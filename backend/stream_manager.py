"""
stream_manager.py
──────────────────
This file makes LIVE STREAMING possible (Mentor requirement #1 and #2).

The problem it solves:
  Your YOLOv8 video processing runs in a background THREAD (because it's
  slow, synchronous code — see run_in_executor in app.py). But your
  WebSocket connections to the React dashboard live in the main ASYNC
  event loop. Threads and asyncio don't talk to each other directly.

The fix:
  StreamManager keeps a reference to the main event loop. When the
  background thread has a new frame to send, it calls
  `broadcast_threadsafe()`, which safely hands the message over to the
  event loop so it can be pushed out over WebSocket to every browser
  tab currently watching that session.

Think of it like a mail slot between two rooms:
  - The YOLO processing thread drops frames in the slot (thread-safe)
  - The asyncio event loop picks them up and delivers them to whoever's
    connected via WebSocket for that session_id
"""

import asyncio
import base64
import json
from typing import Dict, List, Optional

import cv2
import numpy as np
from fastapi import WebSocket


class StreamManager:
    """
    One instance of this is created in app.py and shared by:
      - the WebSocket route (adds/removes browser connections)
      - detector.py's process_video() (pushes frames + stats as they're ready)
    """

    def __init__(self):
        # session_id -> list of active WebSocket connections
        # (more than one browser tab can watch the same session)
        self.connections: Dict[str, List[WebSocket]] = {}

        # The main asyncio event loop, captured at FastAPI startup.
        # Needed so the background thread can safely schedule sends on it.
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    # ─────────────────────────────────────────────────────────
    # Setup — called once from app.py's startup event
    # ─────────────────────────────────────────────────────────
    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

    # ─────────────────────────────────────────────────────────
    # Connection lifecycle — called from the WebSocket route
    # ─────────────────────────────────────────────────────────
    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        self.connections.setdefault(session_id, []).append(websocket)
        print(f"🔌 WebSocket connected for session {session_id} "
              f"({len(self.connections[session_id])} viewer(s))")

    def disconnect(self, session_id: str, websocket: WebSocket):
        conns = self.connections.get(session_id, [])
        if websocket in conns:
            conns.remove(websocket)
        if session_id in self.connections and not self.connections[session_id]:
            del self.connections[session_id]
        print(f"❌ WebSocket disconnected for session {session_id}")

    def has_viewers(self, session_id: str) -> bool:
        """detector.py can check this to skip encoding work if nobody's watching."""
        return bool(self.connections.get(session_id))

    # ─────────────────────────────────────────────────────────
    # Sending — the async part, runs on the main event loop
    # ─────────────────────────────────────────────────────────
    async def _broadcast(self, session_id: str, message: dict):
        conns = self.connections.get(session_id, [])
        if not conns:
            return

        dead_connections = []
        payload = json.dumps(message)

        for ws in conns:
            try:
                await ws.send_text(payload)
            except Exception:
                # Browser tab closed / connection dropped — clean it up
                dead_connections.append(ws)

        for ws in dead_connections:
            self.disconnect(session_id, ws)

    # ─────────────────────────────────────────────────────────
    # Thread-safe entry point — called from the SYNCHRONOUS
    # YOLOv8 processing thread inside detector.py
    # ─────────────────────────────────────────────────────────
    def broadcast_threadsafe(self, session_id: str, message: dict):
        """
        Call this from process_video() in detector.py (regular sync code,
        running inside run_in_executor's background thread).

        `asyncio.run_coroutine_threadsafe` is the standard bridge between
        a background thread and the asyncio event loop — it schedules
        our _broadcast() coroutine to run on the loop and returns
        immediately, so the YOLO thread never blocks waiting on network I/O.
        """
        if self.loop is None:
            return  # loop not set yet (shouldn't happen after startup)

        asyncio.run_coroutine_threadsafe(
            self._broadcast(session_id, message),
            self.loop,
        )

    # ─────────────────────────────────────────────────────────
    # Frame encoding helper
    # ─────────────────────────────────────────────────────────
    @staticmethod
    def encode_frame(frame: np.ndarray, quality: int = 60, max_width: int = 960) -> str:
        """
        Convert an OpenCV frame (numpy array) into a base64 JPEG string
        that can be sent over WebSocket as JSON and displayed in React
        with: <img src={"data:image/jpeg;base64," + data} />

        IMPORTANT: source footage can be 4K (3840x2160) or larger. Encoding
        a full-resolution frame to JPEG and then base64 (~33% size inflation)
        produces a multi-megabyte JSON message PER FRAME — sent every ~40ms
        during live streaming. That is large enough to choke JSON.parse() in
        the browser, or silently fail on some proxies/buffers, which looks
        like "nothing renders" with no obvious server-side error. We resize
        to max_width before encoding — this is a live preview, not the
        archival image (the full-resolution frame is still saved to disk
        separately for violation review).

        Lower quality (60) further keeps bandwidth usage low for live
        streaming — this is a preview stream, not the archival frame saved
        to disk.
        """
        h, w = frame.shape[:2]
        if w > max_width:
            scale = max_width / w
            frame = cv2.resize(frame, (max_width, int(h * scale)), interpolation=cv2.INTER_AREA)

        ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ok:
            return ""
        return base64.b64encode(buffer).decode("utf-8")

    # ─────────────────────────────────────────────────────────
    # Convenience — build + send a "frame" message in one call
    # ─────────────────────────────────────────────────────────
    def send_frame_update(
        self,
        session_id: str,
        frame: np.ndarray,
        frame_number: int,
        stats: dict,
        new_violations: list,
    ):
        """
        Called once per processed frame from detector.py.

        message shape sent to React:
        {
          "type": "frame_update",
          "frame_number": 141,
          "image": "<base64 jpeg, downscaled to max 960px wide>",
          "stats": { "processed_frames": 141, "total_violations": 6, ... },
          "new_violations": [ { "violation_type": "no_helmet", "track_id": "VH04", ... } ]
        }
        """
        if not self.has_viewers(session_id):
            return  # nobody's watching — skip the (relatively costly) JPEG encode

        encoded = self.encode_frame(frame)
        if not encoded:
            # Encoding failed for this frame — still send stats/violations
            # so the dashboard doesn't stall, just skip the image this tick.
            print(f"⚠️  Frame {frame_number}: JPEG encode failed, skipping image for this tick")

        message = {
            "type": "frame_update",
            "frame_number": frame_number,
            "image": encoded,
            "stats": stats,
            "new_violations": new_violations,
        }
        self.broadcast_threadsafe(session_id, message)

    def send_status(self, session_id: str, status: str, extra: dict = None):
        """Used for 'processing_complete', 'error', etc. control messages."""
        message = {"type": "status", "status": status}
        if extra:
            message.update(extra)
        self.broadcast_threadsafe(session_id, message)


# ─────────────────────────────────────────────────────────────
# Singleton instance — imported by both app.py and detector.py
# so they share the exact same connection registry.
# ─────────────────────────────────────────────────────────────
stream_manager = StreamManager()
