import { useState, useRef } from 'react'
import { uploadVideo } from '../api/traffic'
import styles from './VideoUploader.module.css'

export default function VideoUploader({ onSessionCreated }) {
  const [dragging,  setDragging]  = useState(false)
  const [uploading, setUploading] = useState(false)
  const [progress,  setProgress]  = useState(0)
  const [error,     setError]     = useState('')
  const fileRef = useRef()

  const FIELDS = {
    camera_id: 'CAM_01',
    location:  'Hyderabad Junction',
  }

  const [fields, setFields] = useState(FIELDS)

  async function handleFile(file) {
    if (!file) return
    const ext = file.name.split('.').pop().toLowerCase()
    if (!['mp4','avi','mov','mkv'].includes(ext)) {
      setError('Please upload an MP4, AVI, MOV, or MKV file.')
      return
    }
    setError(''); setUploading(true); setProgress(0)
    try {
      const fd = new FormData()
      fd.append('file',      file)
      fd.append('camera_id', fields.camera_id)
      fd.append('location',  fields.location)
      const { data } = await uploadVideo(fd, setProgress)
      onSessionCreated(data.session_id)
    } catch (e) {
      setError(e.response?.data?.detail || 'Upload failed. Is the backend running?')
    } finally {
      setUploading(false)
    }
  }

  const onDrop = e => {
    e.preventDefault(); setDragging(false)
    handleFile(e.dataTransfer.files[0])
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.fields}>
        <label>
          Camera ID
          <input value={fields.camera_id}
            onChange={e => setFields(f => ({...f, camera_id: e.target.value}))} />
        </label>
        <label>
          Location
          <input value={fields.location}
            onChange={e => setFields(f => ({...f, location: e.target.value}))} />
        </label>
      </div>

      <div
        className={`${styles.zone} ${dragging ? styles.over : ''}`}
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => !uploading && fileRef.current.click()}
      >
        <input ref={fileRef} type="file" accept="video/*" hidden
          onChange={e => handleFile(e.target.files[0])} />

        {uploading ? (
          <>
            <div className={styles.spinner} />
            <p className={styles.title}>Uploading & Starting Analysis…</p>
            <div className={styles.bar}><div className={styles.fill} style={{width:`${progress}%`}} /></div>
            <p className={styles.sub}>{progress}% uploaded</p>
          </>
        ) : (
          <>
            <div className={styles.icon}>▲</div>
            <p className={styles.title}>Drop Traffic Video Here</p>
            <p className={styles.sub}>MP4 · AVI · MOV · MKV &nbsp;|&nbsp; Up to 4K resolution</p>
            <button className={styles.btn}>Choose File</button>
          </>
        )}
      </div>
      {error && <p className={styles.err}>{error}</p>}
    </div>
  )
}
