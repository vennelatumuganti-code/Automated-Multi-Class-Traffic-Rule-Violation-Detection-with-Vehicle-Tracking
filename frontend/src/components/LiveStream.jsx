import { useState, useEffect, useRef } from 'react'
import { streamUrl } from '../api/traffic'

/**
 * LiveStream — live annotated video panel (mentor requirements #1 & #2).
 *
 * Deliberately styled with INLINE styles (not a CSS module) so the video
 * always renders at a guaranteed size and in normal document flow — it
 * cannot depend on a stylesheet that might not match your project, and it
 * cannot overlap the cards above it.
 *
 * It opens a WebSocket to /ws/stream/{sessionId}. Each "frame_update"
 * message is one already-annotated JPEG (base64, boxes drawn server-side)
 * plus live stats and any new violations. The last frame stays pinned so
 * the panel never blanks out.
 */
export default function LiveStream({ sessionId, sessionStatus, onNewViolations, fallbackFrameUrl }) {
  const [connected,   setConnected]   = useState(false)
  const [frameData,   setFrameData]   = useState(null)   // base64 jpeg (no prefix)
  const [liveStats,   setLiveStats]   = useState(null)
  const [frameNumber, setFrameNumber] = useState(0)

  const wsRef     = useRef(null)
  const retryRef  = useRef(null)
  const statusRef = useRef(sessionStatus)

  useEffect(() => { statusRef.current = sessionStatus }, [sessionStatus])

  useEffect(() => {
    setFrameData(null)
    setLiveStats(null)
    setFrameNumber(0)
    if (!sessionId) return

    let closedByUs = false

    function connect() {
      const ws = new WebSocket(streamUrl(sessionId))
      wsRef.current = ws

      ws.onopen = () => setConnected(true)

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)
          if (msg.type === 'frame_update') {
            if (msg.image) setFrameData(msg.image)
            setFrameNumber(msg.frame_number)
            setLiveStats(msg.stats)
            if (msg.new_violations?.length && onNewViolations) onNewViolations(msg.new_violations)
          }
          if (msg.type === 'status' && msg.status === 'complete') {
            if (msg.stats) setLiveStats(msg.stats)
          }
        } catch (err) {
          console.error('LiveStream: bad WS message', err)
        }
      }

      ws.onclose = () => {
        setConnected(false)
        if (!closedByUs && statusRef.current === 'processing') {
          retryRef.current = setTimeout(connect, 1500)
        }
      }
      ws.onerror = () => ws.close()
    }

    connect()
    return () => {
      closedByUs = true
      clearTimeout(retryRef.current)
      wsRef.current?.close()
      wsRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId])

  if (!sessionId) return null

  const isLive    = sessionStatus === 'processing'
  const liveSrc   = frameData ? `data:image/jpeg;base64,${frameData}` : null
  const posterSrc = liveSrc || fallbackFrameUrl || null
  const label     = isLive
    ? (connected ? 'Live Feed' : 'Reconnecting…')
    : (liveSrc ? 'Analysis Complete' : (fallbackFrameUrl ? 'Last Processed Frame' : 'Waiting'))

  // ── Inline styles (self-contained, cannot be styled away) ──
  const wrap = {
    position: 'relative', display: 'flex', flexDirection: 'column',
    border: '1px solid var(--border, #E4E8EF)', borderRadius: 14,
    overflow: 'hidden', background: 'var(--panel, #FFFFFF)',
    boxShadow: '0 1px 2px rgba(16,24,40,.05), 0 2px 10px rgba(16,24,40,.05)',
    marginBottom: 16, zIndex: 0,
  }
  const hdr = {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '12px 16px', borderBottom: '1px solid var(--border, #E4E8EF)',
    background: 'var(--surface2, #F7F8FB)',
  }
  const dot = {
    width: 9, height: 9, borderRadius: '50%',
    background: isLive && connected ? 'var(--red, #C81E3A)' : '#94a3b8',
    boxShadow: isLive && connected ? '0 0 0 3px rgba(200,30,58,.18)' : 'none',
  }
  const titleStyle = {
    fontSize: 11, letterSpacing: 1, textTransform: 'uppercase',
    fontWeight: 700, color: 'var(--text, #17202E)',
  }
  // A definite height that CANNOT collapse into a strip and cannot overlap
  // siblings. Scales with the window but stays large and readable.
  const stage = {
    position: 'relative', width: '100%',
    height: 'clamp(340px, 44vw, 620px)',
    background: '#0E1116',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    overflow: 'hidden',
  }
  const img = { width: '100%', height: '100%', objectFit: 'contain', display: 'block' }
  const placeholder = { color: '#9aa4b2', fontSize: 13, padding: 24, textAlign: 'center', maxWidth: 460, lineHeight: 1.6 }

  return (
    <div style={wrap}>
      <div style={hdr}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={dot} />
          <span style={titleStyle}>{label}</span>
        </div>
        {liveStats && (
          <div style={{ fontSize: 12, fontFamily: 'var(--mono, monospace)', color: 'var(--muted, #64748B)' }}>
            Frame {frameNumber} / {liveStats.total_frames || '?'}
          </div>
        )}
      </div>

      <div style={stage}>
        {posterSrc ? (
          <img style={img} src={posterSrc} alt="Annotated traffic frame with detections" />
        ) : (
          <div style={placeholder}>
            {isLive ? 'Waiting for the first analysed frame…'
                    : 'This clip finished before a live viewer connected. Re-upload it to watch the annotated stream.'}
          </div>
        )}
      </div>
    </div>
  )
}
