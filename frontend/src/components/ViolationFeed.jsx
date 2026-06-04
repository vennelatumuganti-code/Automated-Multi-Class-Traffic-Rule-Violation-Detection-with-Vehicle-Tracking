import styles from './ViolationFeed.module.css'

const TYPE_META = {
  no_helmet:     { label: 'No Helmet',      icon: '⛑', cls: 'red'   },
  triple_riding: { label: 'Triple Riding',  icon: '👥', cls: 'amber' },
  signal_jump:   { label: 'Signal Jump',    icon: '🚦', cls: 'red'   },
}

function fmtTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export default function ViolationFeed({ violations = [] }) {
  return (
    <div className={styles.wrap}>
      <div className={styles.hdr}>
        <span className={styles.title}>Live Violation Feed</span>
        <span className={styles.count}>{violations.length}</span>
      </div>

      {violations.length === 0 && (
        <p className={styles.empty}>No violations detected yet.</p>
      )}

      <div className={styles.list}>
        {violations.map((v, i) => {
          const meta = TYPE_META[v.violation_type] || { label: v.violation_type, icon: '⚠', cls: 'red' }
          return (
            <div key={v._id || i} className={styles.item} style={{ animationDelay: `${i * 0.04}s` }}>
              <div className={`${styles.icon} ${styles[meta.cls]}`}>{meta.icon}</div>
              <div className={styles.info}>
                <div className={styles.type}>{meta.label}</div>
                <div className={styles.plate}>
                  {v.vehicle_plate !== 'UNREAD' ? v.vehicle_plate : <span className={styles.unread}>Plate Unread</span>}
                </div>
                <div className={styles.meta2}>
                  Frame #{v.frame_number} &nbsp;·&nbsp;
                  Track {v.track_id} &nbsp;·&nbsp;
                  {v.camera_id} &nbsp;·&nbsp;
                  Conf {(v.confidence * 100).toFixed(0)}%
                </div>
              </div>
              <div className={styles.time}>{fmtTime(v.timestamp)}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
