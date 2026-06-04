import styles from './Topbar.module.css'

export default function Topbar({ sessionStatus }) {
  const isLive = sessionStatus === 'processing'
  return (
    <header className={styles.bar}>
      <div className={styles.logo}>
        <span className={styles.dot} />
        TrafficVision <span className={styles.ai}>AI</span>
      </div>
      <div className={styles.meta}>
        <span className={styles.badge}>BITS Pilani · Vennela Tumuganti · 2024AA05795</span>
        {isLive && (
          <span className={`${styles.badge} ${styles.live}`}>
            <span className={styles.pulse} /> Analyzing
          </span>
        )}
        {sessionStatus === 'done' && (
          <span className={`${styles.badge} ${styles.done}`}>✓ Complete</span>
        )}
      </div>
    </header>
  )
}
