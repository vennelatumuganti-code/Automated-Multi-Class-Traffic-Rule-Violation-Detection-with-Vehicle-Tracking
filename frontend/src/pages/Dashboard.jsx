import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import Topbar         from '../components/Topbar'
import VideoUploader  from '../components/VideoUploader'
import StatsPanel     from '../components/StatsPanel'
import ViolationFeed  from '../components/ViolationFeed'
import VehicleTracker from '../components/VehicleTracker'
import ViolationChart from '../components/ViolationChart'
import FrameStrip     from '../components/FrameStrip'
import LiveStream     from '../components/LiveStream'
import AnalyticsView  from '../components/AnalyticsView'
import { getSessions, getSession, getViolations, getSummary, getVehicles, getFrames } from '../api/traffic'
import styles from './Dashboard.module.css'

export default function Dashboard() {
  const { id: paramId }  = useParams()
  const navigate         = useNavigate()

  const [sessionId,   setSessionId]   = useState(paramId || null)
  const [session,     setSession]     = useState(null)
  const [sessions,    setSessions]    = useState([])
  const [violations,  setViolations]  = useState([])
  const [summary,     setSummary]     = useState({})
  const [vehicles,    setVehicles]    = useState([])
  const [frames,      setFrames]      = useState([])
  const [tab,         setTab]         = useState('violations')  // violations | vehicles | frames
  const [view,        setView]        = useState('session')     // session | analytics — mentor req #5
  const pollRef = useRef(null)

  // Called by <LiveStream> whenever new violations arrive over the
  // WebSocket, so the feed updates instantly instead of waiting for the
  // next 3-second poll cycle.
  const handleNewViolations = useCallback((incoming) => {
    setViolations(prev => {
      const existingFrames = new Set(prev.map(v => `${v.frame_number}-${v.track_id}-${v.violation_type}`))
      const fresh = incoming
        .filter(v => !existingFrames.has(`${v.frame_number}-${v.track_id}-${v.violation_type}`))
        .map(v => ({
          _id: `${v.frame_number}-${v.track_id}-${v.violation_type}`,
          violation_type: v.violation_type,
          vehicle_plate: v.vehicle_plate,
          track_id: v.track_id,
          confidence: v.confidence,
          frame_number: v.frame_number,
          camera_id: session?.camera_id,
          frame_image_path: v.frame_image_path,
          timestamp: new Date().toISOString(),
        }))
      return fresh.length ? [...fresh, ...prev] : prev
    })
  }, [session])

  // Load session list on mount
  useEffect(() => {
    getSessions().then(r => setSessions(r.data.sessions)).catch(() => {})
  }, [])

  // Fetch all data for current session
  const fetchData = useCallback(async (id) => {
    try {
      const [sess, viol, summ, vehs, frms] = await Promise.all([
        getSession(id),
        getViolations(id),
        getSummary(id),
        getVehicles(id),
        getFrames(id),
      ])
      setSession(sess.data)
      setViolations(viol.data.violations)
      setSummary(summ.data.summary)
      setVehicles(vehs.data.vehicles)
      setFrames(frms.data.frames)
    } catch (e) {
      console.error('Fetch error', e)
    }
  }, [])

  // Poll while processing
  useEffect(() => {
    if (!sessionId) return
    fetchData(sessionId)

    pollRef.current = setInterval(() => {
      getSession(sessionId).then(r => {
        setSession(r.data)
        if (r.data.status !== 'processing') {
          clearInterval(pollRef.current)
          fetchData(sessionId)   // final full fetch
        } else {
          // Lightweight refresh of violations/vehicles during processing
          getViolations(sessionId).then(r => setViolations(r.data.violations))
          getVehicles(sessionId).then(r  => setVehicles(r.data.vehicles))
        }
      }).catch(() => {})
    }, 3000)   // poll every 3 seconds

    return () => clearInterval(pollRef.current)
  }, [sessionId, fetchData])

  function handleSessionCreated(id) {
    setSessionId(id)
    navigate(`/session/${id}`)
    getSessions().then(r => setSessions(r.data.sessions)).catch(() => {})
  }

  function switchSession(id) {
    clearInterval(pollRef.current)
    setSessionId(id)
    setSession(null); setViolations([]); setSummary({})
    setVehicles([]); setFrames([])
    navigate(`/session/${id}`)
  }

  return (
    <div className={styles.root}>
      <Topbar sessionStatus={session?.status} />

      <div className={styles.body}>
        {/* ── Left Sidebar ── */}
        <aside className={styles.sidebar}>
          <div className={styles.sideSection}>
            <div className={styles.sideLabel}>New Analysis</div>
            <VideoUploader onSessionCreated={handleSessionCreated} />
          </div>

          <div className={styles.sideSection}>
            <div className={styles.sideLabel}>Past Sessions</div>
            {sessions.length === 0 && <p className={styles.noSess}>No sessions yet.</p>}
            {sessions.map(s => (
              <div
                key={s._id}
                className={`${styles.sessItem} ${s._id === sessionId ? styles.sessActive : ''}`}
                onClick={() => switchSession(s._id)}
              >
                <div className={styles.sessFile}>{s.video_file}</div>
                <div className={styles.sessMeta}>
                  {s.camera_id} · {s.location}
                </div>
                <div className={styles.sessMeta}>
                  {s.total_violations} violations · {s.total_vehicles} vehicles
                </div>
                <span className={`tag ${s.status === 'done' ? 'tag-green' : s.status === 'processing' ? 'tag-amber' : 'tag-gray'}`}>
                  {s.status}
                </span>
              </div>
            ))}
          </div>
        </aside>

        {/* ── Main Content ── */}
        <main className={styles.main}>
          <div className={styles.viewSwitch}>
            <button
              className={`${styles.viewBtn} ${view === 'session' ? styles.viewBtnActive : ''}`}
              onClick={() => setView('session')}
            >
              Session View
            </button>
            <button
              className={`${styles.viewBtn} ${view === 'analytics' ? styles.viewBtnActive : ''}`}
              onClick={() => setView('analytics')}
            >
              Analytics
            </button>
          </div>

          {view === 'analytics' ? (
            <AnalyticsView />
          ) : !sessionId ? (
            <div className={styles.splash}>
              <div className={styles.splashIcon}>▲</div>
              <h2>Upload a traffic video to begin analysis</h2>
              <p>YOLOv8 · ByteTrack · ESRGAN · Tesseract OCR</p>
            </div>
          ) : (
            <>
              {/* Mentor req #1 & #2: live streaming + live YOLO overlay */}
              <LiveStream
                sessionId={sessionId}
                sessionStatus={session?.status}
                onNewViolations={handleNewViolations}
              />
              <StatsPanel session={session} />
              <ViolationChart summary={summary} />
              <FrameStrip frames={frames} violations={violations} />
            </>
          )}
        </main>

        {/* ── Right Panel ── */}
        <aside className={styles.right}>
          <div className={styles.tabs}>
            {['violations','vehicles'].map(t => (
              <button
                key={t}
                className={`${styles.tab} ${tab === t ? styles.tabActive : ''}`}
                onClick={() => setTab(t)}
              >
                {t === 'violations' ? `Violations (${violations.length})` : `Vehicles (${vehicles.length})`}
              </button>
            ))}
          </div>

          <div className={styles.tabContent}>
            {tab === 'violations'
              ? <ViolationFeed violations={violations} />
              : <VehicleTracker vehicles={vehicles} />
            }
          </div>
        </aside>
      </div>
    </div>
  )
}
