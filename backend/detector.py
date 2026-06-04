"""
detector.py
───────────
The heart of the ML pipeline. This file:

  1. Loads YOLOv8 (the object detection model)
  2. Runs detection on each frame → finds vehicles, helmets, riders, plates
  3. Uses ByteTrack (built into YOLOv8) to give each vehicle a persistent ID
  4. Calls the OCR engine to read plate text
  5. Decides what type of violation occurred
  6. Returns structured results to app.py to be saved in MongoDB

Key concepts:
  YOLOv8  — detects what's in each frame and draws a box around it
  ByteTrack — tracks the SAME vehicle across multiple frames, giving it
              a consistent ID (e.g. "VH04") even as it moves
  Confidence — how sure YOLOv8 is about a detection (0.0 to 1.0)
"""

import os
import cv2
import numpy as np
from ultralytics import YOLO
from dotenv import load_dotenv
from frame_extractor import (
    extract_frames,
    save_annotated_frame,
    extract_plate_region,
    timestamp_from_frame,
    get_video_info,
)
from ocr_engine import extract_plate_text
from database import (
    save_violation,
    upsert_vehicle,
    update_session_stats,
    complete_session,
)

load_dotenv()

# ─────────────────────────────────────────────────────────────
# Violation class IDs from your YOLOv8 model
# ─────────────────────────────────────────────────────────────
# When you train YOLOv8 on your dataset, each class gets a number.
# Update these to match YOUR model's class list in data.yaml.
# Example classes from your dissertation:
CLASS_MAP = {
    0: "motorcycle",      # two-wheeler vehicle
    1: "rider",           # person on motorcycle
    2: "helmet",          # helmet being worn
    3: "no_helmet",       # rider without helmet ← violation
    4: "number_plate",    # the license plate region
    5: "triple_riding",   # 3 people on one bike ← violation
    6: "signal_jump",     # vehicle crossing red signal ← violation
}

# Which class IDs count as a traffic violation
VIOLATION_CLASSES = {3: "no_helmet", 5: "triple_riding", 6: "signal_jump"}

# Color for bounding boxes per class (BGR format)
CLASS_COLORS = {
    "motorcycle":    (0, 229, 195),    # teal — normal vehicle
    "rider":         (100, 200, 255),  # light blue — rider
    "helmet":        (0, 200, 100),    # green — compliant
    "no_helmet":     (50, 50, 255),    # red — violation
    "number_plate":  (255, 200, 0),    # amber — plate
    "triple_riding": (50, 50, 255),    # red — violation
    "signal_jump":   (50, 50, 255),    # red — violation
}

CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", 0.5))
FRAME_SKIP           = int(os.getenv("FRAME_SKIP", 3))


# ─────────────────────────────────────────────────────────────
# 1. Load YOLOv8 Model (once at startup)
# ─────────────────────────────────────────────────────────────

class TrafficDetector:
    """
    Wraps YOLOv8 + ByteTrack into one easy-to-use class.
    One instance is created when the app starts and reused for every video.
    """

    def __init__(self, model_path: str = None):
        model_path = model_path or os.getenv("MODEL_PATH", "models/best.pt")

        if not os.path.exists(model_path):
            # If your custom trained model isn't ready yet,
            # fall back to the pre-trained YOLOv8 nano model.
            # It can still detect people and vehicles (not custom violations yet).
            print(f"⚠️  Custom model not found at {model_path}")
            print("   Loading YOLOv8n pretrained model as placeholder...")
            self.model = YOLO("yolov8n.pt")   # downloads automatically on first run
        else:
            print(f"✅ Loading custom model from {model_path}")
            self.model = YOLO(model_path)

        print("✅ TrafficDetector ready")

    def detect_frame(self, frame: np.ndarray) -> list:
        """
        Run YOLOv8 detection on one frame WITH ByteTrack tracking.

        YOLOv8's .track() method:
          - Runs object detection (finds what's in the frame)
          - Runs ByteTrack on top (assigns consistent IDs across frames)
          - Returns a Results object with boxes, class IDs, confidences, and track IDs

        Returns a list of detection dicts, one per detected object.
        """
        # persist=True tells ByteTrack to remember tracks between frames
        results = self.model.track(
            frame,
            persist=True,
            conf=CONFIDENCE_THRESHOLD,
            verbose=False,    # don't print per-frame output to terminal
        )

        detections = []

        # results[0] = detections for the first (and only) image we passed in
        if results[0].boxes is None:
            return detections

        boxes = results[0].boxes

        for i in range(len(boxes)):
            # bbox in [x1, y1, x2, y2] pixel coordinates
            bbox = boxes.xyxy[i].tolist()

            # Class ID (e.g. 3 = no_helmet)
            class_id = int(boxes.cls[i].item())

            # How confident YOLOv8 is (0.0 – 1.0)
            confidence = float(boxes.conf[i].item())

            # Track ID from ByteTrack — same vehicle = same ID across frames
            # ByteTrack might not assign an ID immediately on frame 1
            track_id = None
            if boxes.id is not None:
                track_id = int(boxes.id[i].item())

            class_name = CLASS_MAP.get(class_id, f"class_{class_id}")
            color      = CLASS_COLORS.get(class_name, (200, 200, 200))

            detections.append({
                "bbox":       bbox,
                "class_id":   class_id,
                "class_name": class_name,
                "confidence": confidence,
                "track_id":   track_id,
                "color":      color,
                "is_violation": class_id in VIOLATION_CLASSES,
                "violation_type": VIOLATION_CLASSES.get(class_id),
            })

        return detections


# ─────────────────────────────────────────────────────────────
# 2. Find Number Plate for a Given Vehicle
# ─────────────────────────────────────────────────────────────

def find_plate_for_vehicle(
    frame:      np.ndarray,
    detections: list,
    vehicle_bbox: list,
) -> tuple[str, float]:
    """
    Given a list of all detections in a frame, find the number_plate
    detection that is INSIDE or near the given vehicle's bounding box.

    Logic:
      - Look at all detections with class "number_plate"
      - Find the one whose center falls inside the vehicle bbox
      - Crop that plate region from the frame
      - Run OCR on it

    Returns: (plate_text, ocr_confidence)
    """
    vx1, vy1, vx2, vy2 = vehicle_bbox

    for det in detections:
        if det["class_name"] != "number_plate":
            continue

        px1, py1, px2, py2 = det["bbox"]
        # Check if plate center is inside vehicle box
        plate_cx = (px1 + px2) / 2
        plate_cy = (py1 + py2) / 2

        if vx1 <= plate_cx <= vx2 and vy1 <= plate_cy <= vy2:
            # Crop the plate from the frame
            plate_crop = extract_plate_region(
                frame,
                [px1, py1, px2, py2],
                padding=8
            )
            return extract_plate_text(plate_crop)

    return "UNREAD", 0.0


# ─────────────────────────────────────────────────────────────
# 3. Full Video Processing Pipeline
# ─────────────────────────────────────────────────────────────

def process_video(
    video_path:    str,
    session_id:    str,
    camera_id:     str,
    frames_folder: str,
    detector:      TrafficDetector,
) -> dict:
    """
    Main pipeline function. Called by app.py when user uploads a video.

    Flow:
      For each frame in the video (skipping every Nth):
        1. Run YOLOv8 + ByteTrack → get detections with track IDs
        2. For each violation detection:
           a. Find the associated number plate
           b. Run OCR to get plate text
           c. Save violation to MongoDB
           d. Upsert vehicle record in MongoDB
        3. Draw boxes on the frame and save as JPEG
        4. Update session stats in MongoDB

    Returns a summary dict when complete.
    """
    print(f"\n🎬 Starting analysis: {video_path}")
    print(f"   Session: {session_id} | Camera: {camera_id}")

    # Get video info for progress tracking
    info         = get_video_info(video_path)
    fps          = info["fps"]
    video_file   = os.path.basename(video_path)

    total_violations  = 0
    total_vehicles    = set()     # unique track IDs seen
    plates_recognised = 0
    processed_frames  = 0

    # Make a subfolder for this session's frames
    session_frames_folder = os.path.join(frames_folder, session_id)
    os.makedirs(session_frames_folder, exist_ok=True)

    # ── Frame Loop ──────────────────────────────────────────
    for frame_number, frame in extract_frames(video_path, session_frames_folder, FRAME_SKIP):

        processed_frames += 1

        # Run detection + tracking
        detections = detector.detect_frame(frame)

        # Track which track_ids appear in this frame
        frame_violations = []

        for det in detections:
            track_id = det["track_id"]
            if track_id:
                total_vehicles.add(track_id)

            # ── Handle Violations ────────────────────────────
            if det["is_violation"]:
                violation_type = det["violation_type"]

                # Try to find and read the plate for this vehicle
                plate_text, ocr_conf = find_plate_for_vehicle(
                    frame, detections, det["bbox"]
                )

                if plate_text != "UNREAD":
                    plates_recognised += 1

                # Convert frame number → timestamp string (e.g. "00:48")
                timestamp_str = timestamp_from_frame(frame_number, fps)

                # Save violation to MongoDB
                save_violation(
                    session_id=      session_id,
                    camera_id=       camera_id,
                    video_file=      video_file,
                    track_id=        f"VH{track_id:02d}" if track_id else "UNKNOWN",
                    vehicle_plate=   plate_text,
                    violation_type=  violation_type,
                    confidence=      det["confidence"],
                    frame_number=    frame_number,
                    bbox=            det["bbox"],
                )

                # Upsert vehicle record (create or update)
                if track_id:
                    upsert_vehicle(
                        session_id=     session_id,
                        camera_id=      camera_id,
                        track_id=       f"VH{track_id:02d}",
                        vehicle_plate=  plate_text,
                        violation_type= violation_type,
                        ocr_confidence= ocr_conf,
                        frame_number=   frame_number,
                    )

                total_violations += 1

                # Prepare annotation data for this frame's image
                frame_violations.append({
                    "bbox":  det["bbox"],
                    "label": f"{violation_type.replace('_',' ')} | {plate_text}",
                    "conf":  det["confidence"],
                    "color": det["color"],
                })

        # Save annotated frame image (only if it has violations — saves disk space)
        if frame_violations:
            save_annotated_frame(
                frame=          frame,
                frame_number=   frame_number,
                session_id=     session_id,
                output_folder=  session_frames_folder,
                detections=     frame_violations,
            )

        # Update MongoDB stats every 50 processed frames
        if processed_frames % 50 == 0:
            update_session_stats(session_id, {
                "processed_frames":  processed_frames,
                "total_vehicles":    len(total_vehicles),
                "total_violations":  total_violations,
                "plates_recognised": plates_recognised,
            })
            print(f"   📊 Frame {frame_number} | "
                  f"Violations: {total_violations} | "
                  f"Vehicles: {len(total_vehicles)}")

    # ── Final Stats ──────────────────────────────────────────
    final_stats = {
        "total_frames":      info["total_frames"],
        "processed_frames":  processed_frames,
        "total_vehicles":    len(total_vehicles),
        "total_violations":  total_violations,
        "plates_recognised": plates_recognised,
        "status":            "done",
    }

    # Mark session complete in MongoDB
    update_session_stats(session_id, final_stats)
    complete_session(session_id)

    print(f"\n✅ Analysis complete!")
    print(f"   Violations: {total_violations}")
    print(f"   Vehicles tracked: {len(total_vehicles)}")
    print(f"   Plates read: {plates_recognised}")

    return final_stats
