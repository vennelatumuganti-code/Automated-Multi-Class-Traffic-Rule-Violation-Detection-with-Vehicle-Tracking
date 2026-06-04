import styles from './VehicleTracker.module.css'

export default function VehicleTracker({ vehicles = [] }) {
  return (
    <div className={styles.wrap}>
      <div className={styles.hdr}>
        <span className={styles.title}>Vehicle Tracks</span>
        <span className={styles.count}>{vehicles.length}</span>
      </div>

      {vehicles.length === 0 && (
        <p className={styles.empty}>No vehicles tracked yet.</p>
      )}

      <div className={styles.list}>
        {vehicles.map((v, i) => (
          <div key={v._id || i} className={styles.item} style={{ animationDelay: `${i * 0.03}s` }}>
            <span className={styles.trackId}>{v.track_id}</span>
            <div className={styles.info}>
              <div className={styles.plate}>
                {v.vehicle_plate !== 'UNREAD' ? v.vehicle_plate : <span className={styles.unread}>No Plate</span>}
              </div>
              <div className={styles.frames}>
                Frames {v.first_seen_frame}–{v.last_seen_frame}
              </div>
              {v.violation_types?.length > 0 && (
                <div className={styles.vtypes}>
                  {v.violation_types.map(t => (
                    <span key={t} className="tag tag-red">{t.replace('_',' ')}</span>
                  ))}
                </div>
              )}
            </div>
            <span className={`${styles.status} ${v.violation_status ? styles.viol : styles.ok}`}>
              {v.violation_status ? 'Violated' : 'Clear'}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
