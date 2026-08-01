"""
frame_extractor.py
──────────────────
This file handles reading a video file and pulling out individual
frames (images) from it using OpenCV.

Think of a video as a flipbook — this module "tears out" individual
pages (frames) so YOLOv8 can look at each one and detect violations.

Key concept:
  FPS = Frames Per Second. A 25 FPS video has 25 images per second.
  For a 2-minute video = 120 seconds × 25 = 3,000 frames.
  We don't process every single frame (too slow), so we skip some.
"""

import os
import cv2        # OpenCV — the main computer vision library
import numpy as np
from pathlib import Path
from typing import Generator, Tuple


def get_video_info(video_path: str) -> dict:
    """
    Read basic metadata about the video BEFORE processing.
    This is shown to the user immediately after uploading.

    Returns things like:
      { "fps": 25, "total_frames": 3348, "duration_seconds": 133.9,
        "width": 1920, "height": 1080 }
    """
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        raise ValueError(f"Cannot open video file: {video_path}")

    fps           = cap.get(cv2.CAP_PROP_FPS)
    total_frames  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width         = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height        = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration_secs = total_frames / fps if fps > 0 else 0

    cap.release()   # Always release! Otherwise the file stays locked.

    return {
        "fps":              round(fps, 2),
        "total_frames":     total_frames,
        "duration_seconds": round(duration_secs, 2),
        "width":            width,
        "height":           height,
        "resolution":       f"{width}x{height}",
    }


def extract_frames(
    video_path:   str,
    output_folder: str,
    frame_skip:   int = 3,
) -> Generator[Tuple[int, np.ndarray], None, None]:
    """
    A GENERATOR that yields (frame_number, frame_image) one at a time.

    Why a generator? If we load ALL frames into memory at once, a 2-minute
    HD video would use ~10 GB of RAM. A generator loads only ONE frame
    at a time, processes it, then moves to the next. Memory stays low.

    Arguments:
      video_path    → full path to the .mp4 file
      output_folder → where to save annotated frame images
      frame_skip    → process every Nth frame (3 = every 3rd frame)

    Usage:
      for frame_num, frame in extract_frames("video.mp4", "frames/", 3):
          results = yolo_model(frame)
          # ... do detection ...
    """
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    os.makedirs(output_folder, exist_ok=True)

    frame_number = 0

    while True:
        # Read one frame. ret = True if successful, False at end of video
        ret, frame = cap.read()

        if not ret:
            # End of video — stop the generator
            break

        # Only process every Nth frame (based on frame_skip setting)
        if frame_number % frame_skip == 0:
            yield frame_number, frame

        frame_number += 1

    cap.release()


def draw_boxes(frame: np.ndarray, detections: list = None) -> np.ndarray:
    """
    Draw bounding boxes + labels onto a COPY of a frame and return it.

    This is the single shared drawing routine used by:
      - save_annotated_frame()   → the JPEG saved to disk for a violation
      - detector.py's live loop  → the frame streamed over WebSocket

    Keeping this in one place means the live preview and the saved
    violation image always look identical — same colors, same label style.

    detections = list of dicts like:
      [{ "bbox": [x1,y1,x2,y2], "label": "no_helmet", "conf": 0.94, "color": (255,50,50) }]
    """
    annotated = frame.copy()   # Never draw on the original frame

    if detections:
        for det in detections:
            x1, y1, x2, y2 = [int(v) for v in det["bbox"]]
            label  = det.get("label", "")
            conf   = det.get("conf", 0.0)
            color  = det.get("color", (0, 229, 195))   # default = teal

            # Draw the bounding box rectangle
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

            # Draw a filled rectangle behind the label text for readability
            text   = f"{label} {conf:.0%}"
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(annotated, (x1, y1 - th - 8), (x1 + tw + 6, y1), color, -1)

            # Draw the label text
            cv2.putText(
                annotated, text,
                (x1 + 3, y1 - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                (255, 255, 255),   # white text
                1, cv2.LINE_AA
            )

    return annotated


def save_annotated_frame(
    frame:        np.ndarray,
    frame_number: int,
    session_id:   str,
    output_folder: str,
    detections:   list = None,
) -> str:
    """
    Draw bounding boxes on a frame and save it as a .jpg file.
    These saved images appear in the Frame Strip and the click-to-inspect
    violation detail view on your UI.

    detections = list of dicts like:
      [{ "bbox": [x1,y1,x2,y2], "label": "no_helmet", "conf": 0.94, "color": (255,50,50) }]

    Returns the relative path to the saved image (stored in MongoDB).
    """
    annotated = draw_boxes(frame, detections)

    # Build the output file path
    filename = f"frame_{session_id}_{frame_number:06d}.jpg"
    filepath = os.path.join(output_folder, filename)

    # Save the annotated image
    cv2.imwrite(filepath, annotated)

    return filepath


def extract_plate_region(frame: np.ndarray, bbox: list, padding: int = 10) -> np.ndarray:
    """
    Crop just the number plate area from a frame.
    This cropped image is what gets fed into ESRGAN (super-resolution)
    and then Tesseract OCR to read the plate text.

    padding = extra pixels around the box (helps OCR read edges)
    """
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = bbox

    # Add padding but don't go outside the image boundary
    x1 = max(0, int(x1) - padding)
    y1 = max(0, int(y1) - padding)
    x2 = min(w, int(x2) + padding)
    y2 = min(h, int(y2) + padding)

    return frame[y1:y2, x1:x2]


def timestamp_from_frame(frame_number: int, fps: float) -> str:
    """
    Convert a frame number to a readable MM:SS timestamp.
    Shown in the violation feed: "Frame #0049 → 00:48"
    """
    total_seconds = frame_number / fps if fps > 0 else 0
    minutes = int(total_seconds // 60)
    seconds = int(total_seconds % 60)
    return f"{minutes:02d}:{seconds:02d}"
