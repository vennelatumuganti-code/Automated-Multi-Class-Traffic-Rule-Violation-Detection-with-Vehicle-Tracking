"""
database.py
───────────
This file handles EVERYTHING related to MongoDB.
Think of it as the "librarian" — it knows how to store and
retrieve every piece of data your system produces.

MongoDB concepts (explained simply):
  - Database  → your whole project's data warehouse
  - Collection → like a table in Excel, but flexible
  - Document  → one row of data, stored as JSON
"""

import os
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv
from pymongo import MongoClient, DESCENDING
from bson import ObjectId

# Load values from your .env file
load_dotenv()

# ─────────────────────────────────────────────
# 1. Connect to MongoDB
# ─────────────────────────────────────────────
# MongoClient opens a connection to your local MongoDB server.
# It's like opening a door to the database.
client = MongoClient(os.getenv("MONGODB_URL", "mongodb://localhost:27017"))

# Select (or create) the database named in your .env file.
# MongoDB creates it automatically when you first write data.
db = client[os.getenv("DATABASE_NAME", "traffic_violation_db")]

# ─────────────────────────────────────────────
# 2. Define Collections (like tables)
# ─────────────────────────────────────────────
violations_col = db["violations"]   # Every detected violation goes here
vehicles_col   = db["vehicles"]     # Every unique tracked vehicle goes here
sessions_col   = db["sessions"]     # Every video analysis session goes here


# ─────────────────────────────────────────────
# 3. Create Indexes (makes queries faster)
# ─────────────────────────────────────────────
# An index is like a book's table of contents —
# without it, MongoDB reads every document to find a match.
def create_indexes():
    violations_col.create_index([("session_id", DESCENDING)])
    violations_col.create_index([("vehicle_plate", DESCENDING)])
    violations_col.create_index([("camera_id", DESCENDING)])
    vehicles_col.create_index([("track_id", DESCENDING)])
    vehicles_col.create_index([("session_id", DESCENDING)])
    sessions_col.create_index([("created_at", DESCENDING)])
    print("✅ MongoDB indexes created")


# ─────────────────────────────────────────────
# 4. Session Functions
# A "session" = one video analysis run
# ─────────────────────────────────────────────

def create_session(video_filename: str, camera_id: str, location: str = "Unknown") -> str:
    """
    Call this when a user uploads a new video.
    Returns the session_id string so we can link all
    violations and vehicles to this particular video run.
    """
    doc = {
        "video_file":        video_filename,
        "camera_id":         camera_id,
        "location":          location,
        "total_frames":      0,
        "processed_frames":  0,
        "total_vehicles":    0,
        "total_violations":  0,
        "plates_recognised": 0,
        "status":            "processing",   # processing → done → failed
        "created_at":        datetime.utcnow(),
        "completed_at":      None,
    }
    result = sessions_col.insert_one(doc)
    # MongoDB gives every document a unique _id automatically.
    # We return it as a plain string so FastAPI can send it to the frontend.
    return str(result.inserted_id)


def update_session_stats(session_id: str, stats: dict):
    """Update running totals as frames are processed."""
    sessions_col.update_one(
        {"_id": ObjectId(session_id)},
        {"$set": stats}
    )


def complete_session(session_id: str):
    """Mark the session as done when all frames are processed."""
    sessions_col.update_one(
        {"_id": ObjectId(session_id)},
        {"$set": {"status": "done", "completed_at": datetime.utcnow()}}
    )


def get_all_sessions() -> list:
    """Return all sessions, newest first."""
    docs = sessions_col.find().sort("created_at", DESCENDING)
    return [_serialize(d) for d in docs]


def get_session(session_id: str) -> Optional[dict]:
    """Return one session by ID."""
    doc = sessions_col.find_one({"_id": ObjectId(session_id)})
    return _serialize(doc) if doc else None


# ─────────────────────────────────────────────
# 5. Violation Functions
# One document per detected traffic violation
# ─────────────────────────────────────────────

def save_violation(
    session_id:      str,
    camera_id:       str,
    video_file:      str,
    track_id:        str,
    vehicle_plate:   str,
    violation_type:  str,   # "no_helmet" | "triple_riding" | "signal_jump"
    confidence:      float,
    frame_number:    int,
    bbox:            list,  # [x1, y1, x2, y2] — the box drawn on screen
    frame_image_path: str = "",
) -> str:
    """
    Save one violation event to MongoDB.
    Called once for every violation detected in every frame.
    Returns the new document's ID.
    """
    doc = {
        "session_id":       session_id,
        "camera_id":        camera_id,
        "video_file":       video_file,
        "track_id":         track_id,
        "vehicle_plate":    vehicle_plate,
        "violation_type":   violation_type,
        "confidence":       round(confidence, 3),
        "frame_number":     frame_number,
        "bbox":             bbox,
        "frame_image_path": frame_image_path,  # path to the saved annotated frame
        "timestamp":        datetime.utcnow(),
    }
    result = violations_col.insert_one(doc)
    return str(result.inserted_id)


def get_violations(session_id: str) -> list:
    """Get all violations for one session, newest first."""
    docs = violations_col.find(
        {"session_id": session_id}
    ).sort("frame_number", DESCENDING)
    return [_serialize(d) for d in docs]


def get_violation_summary(session_id: str) -> dict:
    """
    Count violations grouped by type.
    This powers the bar chart on your dashboard.
    Example return:
      { "no_helmet": 14, "triple_riding": 7, "signal_jump": 3 }
    """
    pipeline = [
        {"$match": {"session_id": session_id}},
        {"$group": {"_id": "$violation_type", "count": {"$sum": 1}}},
    ]
    results = violations_col.aggregate(pipeline)
    return {r["_id"]: r["count"] for r in results}


# ─────────────────────────────────────────────
# 6. Vehicle Functions
# One document per unique vehicle track
# ─────────────────────────────────────────────

def upsert_vehicle(
    session_id:      str,
    camera_id:       str,
    track_id:        str,
    vehicle_plate:   str,
    violation_type:  Optional[str] = None,
    ocr_confidence:  float = 0.0,
    frame_number:    int = 0,
):
    """
    'Upsert' means: update if the vehicle already exists, insert if it doesn't.
    We use track_id (from ByteTrack) as the unique key.

    Each time we see a vehicle in a new frame:
    - If new → create a document
    - If seen before → update its last_seen_frame and add any new violations
    """
    filter_query = {"session_id": session_id, "track_id": track_id}

    update = {
        "$set": {
            "camera_id":      camera_id,
            "vehicle_plate":  vehicle_plate,
            "ocr_confidence": round(ocr_confidence, 3),
            "last_seen_frame": frame_number,
            "updated_at":     datetime.utcnow(),
        },
        "$setOnInsert": {
            # These fields only set when document is FIRST created
            "first_seen_frame": frame_number,
            "created_at":       datetime.utcnow(),
        },
        "$addToSet": {},   # prevents duplicate violation types
    }

    # Only add violation_type to the list if there actually is one
    if violation_type:
        update["$addToSet"]["violation_types"] = violation_type
        update["$set"]["violation_status"] = True
    else:
        update.setdefault("$setOnInsert", {})
        update["$setOnInsert"].setdefault("violation_types", [])
        update["$setOnInsert"].setdefault("violation_status", False)

    vehicles_col.update_one(filter_query, update, upsert=True)


def get_vehicles(session_id: str) -> list:
    """Get all tracked vehicles for one session."""
    docs = vehicles_col.find({"session_id": session_id})
    return [_serialize(d) for d in docs]


# ─────────────────────────────────────────────
# 7. Helper — Fix MongoDB ObjectId
# ─────────────────────────────────────────────
def _serialize(doc: dict) -> dict:
    """
    MongoDB stores IDs as ObjectId objects, not plain strings.
    JSON can't serialize ObjectId, so we convert it to a string.
    This is called on every document before sending to the frontend.
    """
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc
