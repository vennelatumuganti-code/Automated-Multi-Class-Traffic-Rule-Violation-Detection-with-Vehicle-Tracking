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

// ── Robust frame URL builder ────────────────────────────────
// The backend may store the annotated-frame path in different shapes:
//   "/frames/<sess>/frame_x.jpg"        (correct URL)
//   "frames/<sess>/frame_x.jpg"         (relative, no leading slash)
//   "frames\\<sess>\\frame_x.jpg"       (Windows backslashes)
//   "C:\\...\\backend\\frames\\<sess>\\frame_x.jpg"  (absolute)
// The app serves the frames folder at /frames, so we normalise ANY of the
// above down to  http://localhost:8000/frames/<sess>/<file>.jpg
export const frameUrl = (path) => {
  if (!path) return null
  let p = String(path).replace(/\\/g, '/')       // backslashes → forward slashes
  const idx = p.indexOf('frames/')               // keep from the 'frames/' segment on
  if (idx >= 0) p = '/' + p.slice(idx)
  else if (!p.startsWith('/')) p = '/' + p
  return `${BASE}${p}`
}

// ── Live Streaming (mentor requirements #1 and #2) ──────────
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
