import styles from './StatsPanel.module.css'

export default function StatsPanel({ session }) {
  if (!session) return null

  const pct = session.total_frames > 0
    ? Math.round(session.processed_frames / session.total_frames * 100)
    : 0

  const cards = [
    { label: 'Violations',       value: session.total_violations  ?? 0, color: 'red'   },
    { label: 'Vehicles Tracked', value: session.total_vehicles    ?? 0, color: 'white' },
    { label: 'Frames Processed', value: (session.processed_frames ?? 0).toLocaleString(), color: 'green' },
    { label: 'Plates Read',      value: session.plates_recognised ?? 0, color: 'amber' },
  ]

  return (
    <div className={styles.wrap}>
      {cards.map(c => (
        <div key={c.label} className={styles.card}>
          <div className={styles.label}>{c.label}</div>
          <div className={`${styles.val} ${styles[c.color]}`}>{c.value}</div>
          {c.label === 'Frames Processed' && session.status === 'processing' && (
            <div className={styles.progBar}>
              <div className={styles.progFill} style={{ width: `${pct}%` }} />
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
