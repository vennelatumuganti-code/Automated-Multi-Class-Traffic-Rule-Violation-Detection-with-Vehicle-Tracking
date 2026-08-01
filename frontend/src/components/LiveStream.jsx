import { useState, useEffect, useRef } from 'react'
import { streamUrl } from '../api/traffic'
import styles from './LiveStream.module.css'

/**
 * LiveStream
 * ──────────
 * Mentor requirements #1 and #2:
 *   1. Live streaming to the dashboard
 *   2. A live video panel with YOLO bounding-box overlays showing
 *      vehicles moving in real time
 *
 * How it works:
 *   Opens a WebSocket to /ws/stream/{sessionId} (see backend/app.py +
 *   stream_manager.py). Every message is one already-annotated JPEG
 *   frame (base64) plus running stats and any brand-new violations —
 *   sent live by detector.py as it processes the video.
 *
 * This component owns the connection lifecycle: it reconnects if the
 * session is still "processing" and the socket drops, and cleanly
 * closes when you switch sessions or leave the page.
 */
export default function LiveStream({ sessionId, sessionStatus, onNewViolations }) {
  const [connected,    setConnected]    = useState(false)
  const [frameData,    setFrameData]    = useState(null)   // base64 jpeg
  const [liveStats,    setLiveStats]    = useState(null)
  const [frameNumber,  setFrameNumber]  = useState(0)
  const wsRef      = useRef(null)
  const retryRef    = useRef(null)

  useEffect(() => {
    if (!sessionId) return

    function connect() {
      const ws = new WebSocket(streamUrl(sessionId))
      wsRef.current = ws

      ws.onopen = () => setConnected(true)

      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data)

        if (msg.type === 'frame_update') {
          setFrameData(msg.image)
          setFrameNumber(msg.frame_number)
          setLiveStats(msg.stats)
          if (msg.new_violations?.length && onNewViolations) {
            onNewViolations(msg.new_violations)
          }
        }

        if (msg.type === 'status' && msg.status === 'complete') {
          setLiveStats(msg.stats)
        }
      }

      ws.onclose = () => {
        setConnected(false)
        // If the video is still processing, the socket likely dropped
        // unexpectedly (not because processing finished) — try again.
        if (sessionStatus === 'processing') {
          retryRef.current = setTimeout(connect, 1500)
        }
      }

      ws.onerror = () => ws.close()
    }

    connect()

    return () => {
      clearTimeout(retryRef.current)
      wsRef.current?.close()
      wsRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId])

  if (!sessionId) return null

  const isLive = sessionStatus === 'processing'

  return (
    <div className={styles.wrap}>
      <div className={styles.hdr}>
        <div className={styles.hdrLeft}>
          <span className={`${styles.dot} ${isLive && connected ? styles.dotLive : styles.dotOff}`} />
          <span className={styles.title}>
            {isLive ? (connected ? 'Live Feed' : 'Reconnecting…') : 'Playback Ended'}
          </span>
        </div>
        {liveStats && (
          <div className={styles.hdrRight}>
            Frame {frameNumber} / {liveStats.total_frames || '?'}
          </div>
        )}
      </div>

      <div className={styles.videoArea}>
        {frameData ? (
          <img
            className={styles.frame}
            src={`data:image/jpeg;base64,${frameData}`}
            alt="Live annotated video frame"
          />
        ) : (
          <div className={styles.placeholder}>
            {isLive ? 'Waiting for first frame…' : 'No live frames for this session yet.'}
          </div>
        )}
      </div>

      {liveStats && (
        <div className={styles.statsBar}>
          <div className={styles.statItem}>
            <span className={styles.statVal}>{liveStats.total_vehicles}</span>
            <span className={styles.statLabel}>Vehicles</span>
          </div>
          <div className={styles.statItem}>
            <span className={`${styles.statVal} ${styles.statRed}`}>{liveStats.total_violations}</span>
            <span className={styles.statLabel}>Violations</span>
          </div>
          <div className={styles.statItem}>
            <span className={styles.statVal}>{liveStats.plates_recognised}</span>
            <span className={styles.statLabel}>Plates Read</span>
          </div>
        </div>
      )}
    </div>
  )
}
