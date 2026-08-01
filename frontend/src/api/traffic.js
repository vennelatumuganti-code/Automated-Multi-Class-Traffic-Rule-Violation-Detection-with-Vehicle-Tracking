import axios from 'axios'

const BASE    = 'http://localhost:8000'
const WS_BASE = 'ws://localhost:8000'
const api     = axios.create({ baseURL: BASE })

export const uploadVideo    = (formData, onProgress) =>
  api.post('/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: e => onProgress && onProgress(Math.round(e.loaded * 100 / e.total))
  })

export const getSessions    = ()           => api.get('/sessions')
export const getSession     = (id)         => api.get(`/sessions/${id}`)
export const getViolations  = (id)         => api.get(`/violations/${id}`)
export const getSummary     = (id)         => api.get(`/violations/${id}/summary`)
export const getVehicles    = (id)         => api.get(`/vehicles/${id}`)
export const getFrames      = (id)         => api.get(`/frames/${id}`)
export const frameUrl       = (path)       => `${BASE}${path}`

// ── Live Streaming (mentor requirements #1 and #2) ──────────
// Builds the WebSocket URL a component connects to for a given session.
// Usage: const ws = new WebSocket(streamUrl(sessionId))
export const streamUrl = (sessionId) => `${WS_BASE}/ws/stream/${sessionId}`

// ── Analytics (mentor requirement #5) ───────────────────────
export const getCameras          = ()                    => api.get('/analytics/cameras')

export const getCameraAnalytics  = (cameraId, start, end) =>
  api.get('/analytics/by-camera', { params: { camera_id: cameraId, start, end } })

export const getVehicleAnalytics = (plateOrTrackId, isTrackId, start, end) =>
  api.get('/analytics/by-vehicle', {
    params: {
      vehicle_plate: isTrackId ? undefined : plateOrTrackId,
      track_id:      isTrackId ? plateOrTrackId : undefined,
      start, end,
    }
  })

export const searchVehicles      = (query)                => api.get('/analytics/vehicles/search', { params: { q: query } })
