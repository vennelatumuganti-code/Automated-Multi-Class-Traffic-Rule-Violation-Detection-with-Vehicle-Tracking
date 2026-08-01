import { frameUrl } from '../api/traffic'
import styles from './ViolationModal.module.css'

const TYPE_LABEL = {
  no_helmet:     'No Helmet',
  triple_riding: 'Triple Riding',
  signal_jump:   'Signal Jump',
}

/**
 * ViolationModal
 * ──────────────
 * Mentor requirement #4: "When you click each violation, you should get
 * the image from the folder and show it, along with the violation details."
 *
 * Reads `frame_image_path` off the violation record (now correctly saved —
 * see the detector.py fix) and loads it via the /frames static mount that
 * app.py already exposes.
 */
export default function ViolationModal({ violation, onClose }) {
  if (!violation) return null

  const imagePath = violation.frame_image_path
  const imageSrc   = imagePath ? frameUrl(imagePath) : null

  function handleBackdropClick(e) {
    if (e.target === e.currentTarget) onClose()
  }

  return (
    <div className={styles.backdrop} onClick={handleBackdropClick}>
      <div className={styles.modal}>
        <button className={styles.closeBtn} onClick={onClose} aria-label="Close">✕</button>

        <div className={styles.imageWrap}>
          {imageSrc ? (
            <img className={styles.image} src={imageSrc} alt="Violation frame" />
          ) : (
            <div className={styles.noImage}>No saved image for this violation.</div>
          )}
        </div>

        <div className={styles.details}>
          <div className={styles.typeRow}>
            <span className={styles.typeTag}>
              {TYPE_LABEL[violation.violation_type] || violation.violation_type}
            </span>
            <span className={styles.confidence}>
              {(violation.confidence * 100).toFixed(0)}% confidence
            </span>
          </div>

          <dl className={styles.grid}>
            <dt>Vehicle Plate</dt>
            <dd>{violation.vehicle_plate !== 'UNREAD' ? violation.vehicle_plate : 'Unread'}</dd>

            <dt>Track ID</dt>
            <dd>{violation.track_id}</dd>

            <dt>Camera</dt>
            <dd>{violation.camera_id}</dd>

            <dt>Frame Number</dt>
            <dd>#{violation.frame_number}</dd>

            <dt>Video File</dt>
            <dd className={styles.truncate}>{violation.video_file}</dd>

            <dt>Detected At</dt>
            <dd>{violation.timestamp ? new Date(violation.timestamp).toLocaleString() : '—'}</dd>
          </dl>
        </div>
      </div>
    </div>
  )
}
