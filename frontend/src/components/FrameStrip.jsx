import { useState } from 'react'
import { frameUrl } from '../api/traffic'
import styles from './FrameStrip.module.css'

export default function FrameStrip({ frames = [], violations = [] }) {
  const [active, setActive] = useState(null)

  // Build a set of frame numbers that have violations
  const violatedFrames = new Set(violations.map(v => v.frame_number))

  const current = active != null ? frames.find(f => f.frame_number === active) : null

  return (
    <div className={styles.wrap}>
      {/* Large preview */}
      {current ? (
        <div className={styles.preview}>
          <img src={frameUrl(current.url)} alt={`Frame ${current.frame_number}`} className={styles.previewImg} />
          <div className={styles.previewLabel}>Frame #{current.frame_number}</div>
        </div>
      ) : (
        <div className={styles.noPreview}>
          {frames.length > 0 ? 'Click a frame below to preview' : 'Annotated frames will appear here after analysis'}
        </div>
      )}

      {/* Thumbnail strip */}
      {frames.length > 0 && (
        <div className={styles.strip}>
          {frames.map(f => (
            <div
              key={f.frame_number}
              className={`${styles.thumb} ${active === f.frame_number ? styles.activeThumb : ''}`}
              onClick={() => setActive(f.frame_number)}
            >
              <img src={frameUrl(f.url)} alt="" className={styles.thumbImg} />
              {violatedFrames.has(f.frame_number) && <span className={styles.flag} />}
              <span className={styles.num}>#{f.frame_number}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
