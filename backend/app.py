"""
app.py
──────
The main FastAPI server. This is the file you run to start the backend.
It defines all the API "endpoints" — the URLs your React frontend calls.

How to run this file:
  cd backend
  uvicorn app:app --reload --port 8000

What "endpoint" means:
  An endpoint is a URL + an action. Examples:
    POST /upload     → "receive this video file"
    GET  /violations → "give me the list of violations"
    GET  /sessions   → "give me the list of video sessions"

After starting, visit http://localhost:8000/docs
  → FastAPI auto-generates an interactive API testing page!
     You can test every endpoint without writing any frontend code.
"""

import os
import uuid
import asyncio
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import aiofiles
from dotenv import load_dotenv

# Import our own modules
from database import (
    create_indexes,
    create_session,
    get_session,
    get_all_sessions,
    get_violations,
    get_violation_summary,
    get_vehicles,
)
from detector import TrafficDetector, process_video

load_dotenv()

# ─────────────────────────────────────────────────────────────
# 1. Create the FastAPI App
# ─────────────────────────────────────────────────────────────
app = FastAPI(
    title="TrafficVision AI — Backend API",
    description="Hybrid Deep Learning Traffic Violation Analysis System",
    version="1.0.0",
)

# ─────────────────────────────────────────────────────────────
# 2. CORS Middleware
# ─────────────────────────────────────────────────────────────
# CORS = Cross-Origin Resource Sharing
# Your React app runs on http://localhost:5173
# Your API runs on http://localhost:8000
# Browsers block requests between different ports by default.
# This middleware says "it's okay, allow React to talk to us".
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],    # allow GET, POST, DELETE, etc.
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────
# 3. Folder Setup
# ─────────────────────────────────────────────────────────────
UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploads")
FRAMES_FOLDER = os.getenv("FRAMES_FOLDER", "frames")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(FRAMES_FOLDER, exist_ok=True)

# Serve the frames folder as static files so React can display frame images
# e.g. http://localhost:8000/frames/sess_001/frame_000042.jpg
app.mount("/frames", StaticFiles(directory=FRAMES_FOLDER), name="frames")

# ─────────────────────────────────────────────────────────────
# 4. Startup — Load ML Model + Create DB Indexes
# ─────────────────────────────────────────────────────────────
detector: Optional[TrafficDetector] = None

@app.on_event("startup")
async def startup_event():
    """
    This runs automatically when the server starts.
    We load YOLOv8 here so it's ready before any request comes in.
    Loading takes ~5 seconds — we want to pay that cost once at startup.
    """
    global detector
    print("🚀 Starting TrafficVision AI Backend...")
    create_indexes()           # Set up MongoDB indexes
    detector = TrafficDetector()   # Load YOLOv8
    print("✅ Backend ready at http://localhost:8000")
    print("📖 API docs at http://localhost:8000/docs")


# ─────────────────────────────────────────────────────────────
# 5. Root — Health Check
# ─────────────────────────────────────────────────────────────
@app.get("/")
def root():
    """
    Simple health check. Visit http://localhost:8000 to confirm the server is running.
    """
    return {"status": "running", "message": "TrafficVision AI Backend is live ✅"}


# ─────────────────────────────────────────────────────────────
# 6. POST /upload — Upload a Video File
# ─────────────────────────────────────────────────────────────
@app.post("/upload")
async def upload_video(
    background_tasks: BackgroundTasks,       # runs analysis after response is sent
    file:       UploadFile = File(...),      # the video file from the frontend
    camera_id:  str  = Form("CAM_01"),       # which camera this footage is from
    location:   str  = Form("Unknown"),      # e.g. "Kukatpally Junction"
):
    """
    Step 1: Receive the video file and save it to disk.
    Step 2: Create a session record in MongoDB.
    Step 3: Start the ML analysis in the background (so the frontend
            doesn't have to wait — it gets a session_id immediately).

    React calls this with:
      const formData = new FormData()
      formData.append("file", videoFile)
      formData.append("camera_id", "CAM_01")
      await axios.post("http://localhost:8000/upload", formData)
    """
    # Validate file type
    allowed_extensions = {".mp4", ".avi", ".mov", ".mkv"}
    suffix = Path(file.filename).suffix.lower()
    if suffix not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {suffix}. Use MP4, AVI, MOV, or MKV."
        )

    # Generate a unique filename to avoid overwriting existing files
    unique_name = f"{uuid.uuid4().hex}{suffix}"
    save_path   = os.path.join(UPLOAD_FOLDER, unique_name)

    # Save the uploaded file to disk (async = doesn't block other requests)
    async with aiofiles.open(save_path, "wb") as f:
        content = await file.read()
        await f.write(content)

    print(f"📁 Video saved: {save_path} ({len(content) / 1024 / 1024:.1f} MB)")

    # Create a session in MongoDB — returns a session_id string
    session_id = create_session(
        video_filename=unique_name,
        camera_id=camera_id,
        location=location,
    )

    # Run the ML pipeline in the background
    # BackgroundTasks sends the response FIRST, then starts analysis.
    # So React gets the session_id immediately and can start polling for results.
    background_tasks.add_task(
        run_analysis_task,
        video_path=    save_path,
        session_id=    session_id,
        camera_id=     camera_id,
        frames_folder= FRAMES_FOLDER,
    )

    return {
        "success":    True,
        "session_id": session_id,
        "message":    "Video uploaded. Analysis started in background.",
        "filename":   unique_name,
    }


async def run_analysis_task(
    video_path: str,
    session_id: str,
    camera_id:  str,
    frames_folder: str,
):
    """
    Wraps the synchronous process_video() in an async-compatible way.
    FastAPI is async but YOLOv8 is synchronous — this bridges them.
    """
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,  # uses default ThreadPoolExecutor
        process_video,
        video_path, session_id, camera_id, frames_folder, detector
    )


# ─────────────────────────────────────────────────────────────
# 7. GET /sessions — List All Video Sessions
# ─────────────────────────────────────────────────────────────
@app.get("/sessions")
def list_sessions():
    """
    Returns all video analysis sessions, newest first.
    React uses this to populate the session selector dropdown.

    Example response:
    [
      { "session_id": "...", "camera_id": "CAM_01",
        "video_file": "abc.mp4", "status": "done",
        "total_violations": 24, "total_vehicles": 137 }
    ]
    """
    sessions = get_all_sessions()
    return {"sessions": sessions, "count": len(sessions)}


# ─────────────────────────────────────────────────────────────
# 8. GET /sessions/{session_id} — Single Session Status
# ─────────────────────────────────────────────────────────────
@app.get("/sessions/{session_id}")
def get_session_status(session_id: str):
    """
    Get status and stats for one session.
    React polls this every 2 seconds while status = "processing"
    to update the progress bar and live stats cards.

    Returns:
      { "status": "processing", "processed_frames": 1200,
        "total_frames": 3348, "total_violations": 10 }
    """
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


# ─────────────────────────────────────────────────────────────
# 9. GET /violations/{session_id} — All Violations for a Session
# ─────────────────────────────────────────────────────────────
@app.get("/violations/{session_id}")
def list_violations(session_id: str):
    """
    Returns every violation detected in a session.
    This powers the Violation Feed panel on the right side of the UI.

    Example response:
    {
      "violations": [
        { "vehicle_plate": "TS09 EA 4421", "violation_type": "no_helmet",
          "confidence": 0.94, "frame_number": 49, "track_id": "VH04",
          "camera_id": "CAM_01", "timestamp": "2026-05-24T10:32:15" }
      ],
      "count": 24
    }
    """
    violations = get_violations(session_id)
    return {"violations": violations, "count": len(violations)}


# ─────────────────────────────────────────────────────────────
# 10. GET /violations/{session_id}/summary — Chart Data
# ─────────────────────────────────────────────────────────────
@app.get("/violations/{session_id}/summary")
def violation_summary(session_id: str):
    """
    Returns violation counts grouped by type.
    Used to draw the breakdown bar chart on the dashboard.

    Example response:
    {
      "summary": { "no_helmet": 14, "triple_riding": 7, "signal_jump": 3 }
    }
    """
    summary = get_violation_summary(session_id)
    return {"summary": summary}


# ─────────────────────────────────────────────────────────────
# 11. GET /vehicles/{session_id} — Tracked Vehicles
# ─────────────────────────────────────────────────────────────
@app.get("/vehicles/{session_id}")
def list_vehicles(session_id: str):
    """
    Returns all unique vehicles tracked in a session.
    Powers the Vehicle Tracker panel showing track IDs and plates.

    Example response:
    {
      "vehicles": [
        { "track_id": "VH04", "vehicle_plate": "TS09 EA 4421",
          "violation_status": true, "violation_types": ["no_helmet"],
          "first_seen_frame": 42, "last_seen_frame": 89 }
      ],
      "count": 137
    }
    """
    vehicles = get_vehicles(session_id)
    return {"vehicles": vehicles, "count": len(vehicles)}


# ─────────────────────────────────────────────────────────────
# 12. GET /frames/{session_id} — List Annotated Frames
# ─────────────────────────────────────────────────────────────
@app.get("/frames/{session_id}")
def list_frames(session_id: str):
    """
    Returns URLs of all annotated frame images saved for this session.
    The React Frame Strip fetches these to show thumbnail previews.

    Images are served as static files from /frames/{session_id}/*.jpg
    so React can display them with a plain <img src="..."> tag.

    Example response:
    {
      "frames": [
        { "frame_number": 42, "url": "/frames/sess_001/frame_sess_001_000042.jpg" }
      ]
    }
    """
    session_frames_folder = os.path.join(FRAMES_FOLDER, session_id)

    if not os.path.exists(session_frames_folder):
        return {"frames": [], "count": 0}

    frame_files = sorted(
        [f for f in os.listdir(session_frames_folder) if f.endswith(".jpg")]
    )

    frames = []
    for filename in frame_files:
        # Extract frame number from filename: frame_sessid_000042.jpg → 42
        try:
            frame_num = int(filename.split("_")[-1].replace(".jpg", ""))
        except ValueError:
            frame_num = 0

        frames.append({
            "frame_number": frame_num,
            "filename":     filename,
            "url":          f"/frames/{session_id}/{filename}",
        })

    return {"frames": frames, "count": len(frames)}
