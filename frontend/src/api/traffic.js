import axios from 'axios'

const BASE = 'http://localhost:8000'
const api   = axios.create({ baseURL: BASE })

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
