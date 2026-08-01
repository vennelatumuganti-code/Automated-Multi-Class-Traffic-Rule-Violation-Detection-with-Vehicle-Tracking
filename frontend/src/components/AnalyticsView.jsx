import { useState, useEffect, useCallback } from 'react'
import {
  getCameras, getCameraAnalytics, getVehicleAnalytics, searchVehicles,
} from '../api/traffic'
import ViolationModal from './ViolationModal'
import styles from './AnalyticsView.module.css'

const TYPE_LABEL = {
  no_helmet:     'No Helmet',
  triple_riding: 'Triple Riding',
  signal_jump:   'Signal Jump',
}

function BreakdownPills({ breakdown = {} }) {
  const entries = Object.entries(breakdown)
  if (entries.length === 0) return <span className={styles.muted}>—</span>
  return (
    <div className={styles.pills}>
      {entries.map(([type, count]) => (
        <span key={type} className={styles.pill}>
          {TYPE_LABEL[type] || type}: <strong>{count}</strong>
        </span>
      ))}
    </div>
  )
}

function ViolationsTable({ violations, onSelect, showCameraCol }) {
  if (!violations || violations.length === 0) {
    return <p className={styles.empty}>No violations in this range.</p>
  }
  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th>Type</th>
          <th>Plate</th>
          {showCameraCol && <th>Camera</th>}
          <th>Track</th>
          <th>Frame</th>
          <th>When</th>
        </tr>
      </thead>
      <tbody>
        {violations.map((v, i) => (
          <tr key={v._id || i} onClick={() => onSelect(v)}>
            <td>{TYPE_LABEL[v.violation_type] || v.violation_type}</td>
            <td className={styles.mono}>{v.vehicle_plate !== 'UNREAD' ? v.vehicle_plate : '—'}</td>
            {showCameraCol && <td>{v.camera_id}</td>}
            <td className={styles.mono}>{v.track_id}</td>
            <td className={styles.mono}>#{v.frame_number}</td>
            <td>{v.timestamp ? new Date(v.timestamp).toLocaleString() : '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

/**
 * AnalyticsView
 * ─────────────
 * Mentor requirement #5: two dashboard views, each filterable by time span:
 *   - Camera view:  at a camera, how many violations, of what types?
 *   - Vehicle view: for a vehicle, how many times, at which cameras?
 */
export default function AnalyticsView() {
  const [mode, setMode] = useState('camera')   // 'camera' | 'vehicle'
  const [start, setStart] = useState('')
  const [end, setEnd]     = useState('')
  const [selected, setSelected] = useState(null)   // for click-to-inspect modal

  // ── Camera view state ──────────────────────────────────
  const [cameras, setCameras]           = useState([])
  const [cameraId, setCameraId]         = useState('')
  const [cameraSummary, setCameraSummary] = useState([])   // all-cameras overview
  const [cameraDetail, setCameraDetail]   = useState(null) // single-camera drilldown

  // ── Vehicle view state ─────────────────────────────────
  const [vehicleQuery, setVehicleQuery]     = useState('')
  const [vehicleResults, setVehicleResults] = useState([])
  const [vehicleDetail, setVehicleDetail]   = useState(null)

  useEffect(() => {
    getCameras().then(r => setCameras(r.data.cameras)).catch(() => {})
  }, [])

  const loadCameraView = useCallback(() => {
    getCameraAnalytics(cameraId || undefined, start || undefined, end || undefined)
      .then(r => {
        if (cameraId) { setCameraDetail(r.data); setCameraSummary([]) }
        else          { setCameraSummary(r.data.cameras); setCameraDetail(null) }
      })
      .catch(() => {})
  }, [cameraId, start, end])

  useEffect(() => {
    if (mode === 'camera') loadCameraView()
  }, [mode, loadCameraView])

  function handleVehicleSearchChange(q) {
    setVehicleQuery(q)
    if (q.length >= 1) {
      searchVehicles(q).then(r => setVehicleResults(r.data.results)).catch(() => {})
    } else {
      setVehicleResults([])
    }
  }

  function pickVehicle(v) {
    setVehicleQuery(v.vehicle_plate !== 'UNREAD' ? v.vehicle_plate : v.track_id)
    setVehicleResults([])
    const isTrackOnly = v.vehicle_plate === 'UNREAD'
    getVehicleAnalytics(
      isTrackOnly ? v.track_id : v.vehicle_plate,
      isTrackOnly,
      start || undefined,
      end || undefined,
    ).then(r => setVehicleDetail(r.data)).catch(() => {})
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.tabs}>
        <button
          className={`${styles.tab} ${mode === 'camera' ? styles.tabActive : ''}`}
          onClick={() => setMode('camera')}
        >
          By Camera
        </button>
        <button
          className={`${styles.tab} ${mode === 'vehicle' ? styles.tabActive : ''}`}
          onClick={() => setMode('vehicle')}
        >
          By Vehicle
        </button>
      </div>

      <div className={styles.filters}>
        <label className={styles.filterLabel}>
          From
          <input type="date" value={start} onChange={e => setStart(e.target.value)} className={styles.dateInput} />
        </label>
        <label className={styles.filterLabel}>
          To
          <input type="date" value={end} onChange={e => setEnd(e.target.value)} className={styles.dateInput} />
        </label>
        <button
          className={styles.applyBtn}
          onClick={() => mode === 'camera'
            ? loadCameraView()
            : (vehicleDetail && pickVehicle({ vehicle_plate: vehicleDetail.vehicle_plate || 'UNREAD', track_id: vehicleDetail.track_id }))
          }
        >
          Apply
        </button>
      </div>

      {mode === 'camera' && (
        <div className={styles.panel}>
          <select
            className={styles.select}
            value={cameraId}
            onChange={e => setCameraId(e.target.value)}
          >
            <option value="">All Cameras (overview)</option>
            {cameras.map(c => <option key={c} value={c}>{c}</option>)}
          </select>

          {!cameraId && (
            <>
              <p className={styles.hint}>
                Select a camera above to drill into its violation list, or browse the overview below.
              </p>
              <table className={styles.table}>
                <thead>
                  <tr><th>Camera</th><th>Total Violations</th><th>Breakdown</th></tr>
                </thead>
                <tbody>
                  {cameraSummary.map(row => (
                    <tr key={row.camera_id} onClick={() => setCameraId(row.camera_id)} className={styles.clickableRow}>
                      <td>{row.camera_id}</td>
                      <td className={styles.mono}>{row.total_violations}</td>
                      <td><BreakdownPills breakdown={row.breakdown} /></td>
                    </tr>
                  ))}
                  {cameraSummary.length === 0 && (
                    <tr><td colSpan={3} className={styles.empty}>No violations recorded yet.</td></tr>
                  )}
                </tbody>
              </table>
            </>
          )}

          {cameraId && cameraDetail && (
            <>
              <div className={styles.summaryRow}>
                <div className={styles.summaryCard}>
                  <span className={styles.summaryVal}>{cameraDetail.total_violations}</span>
                  <span className={styles.summaryLabel}>Total Violations · {cameraDetail.camera_id}</span>
                </div>
                <BreakdownPills breakdown={cameraDetail.breakdown} />
              </div>
              <ViolationsTable
                violations={cameraDetail.violations}
                onSelect={setSelected}
                showCameraCol={false}
              />
            </>
          )}
        </div>
      )}

      {mode === 'vehicle' && (
        <div className={styles.panel}>
          <div className={styles.searchWrap}>
            <input
              type="text"
              placeholder="Search by plate or track ID (e.g. TS09EA4421 or VH04)…"
              value={vehicleQuery}
              onChange={e => handleVehicleSearchChange(e.target.value)}
              className={styles.searchInput}
            />
            {vehicleResults.length > 0 && (
              <div className={styles.dropdown}>
                {vehicleResults.map(v => (
                  <div key={v._id} className={styles.dropdownItem} onClick={() => pickVehicle(v)}>
                    <span className={styles.mono}>
                      {v.vehicle_plate !== 'UNREAD' ? v.vehicle_plate : v.track_id}
                    </span>
                    <span className={styles.muted}>
                      {v.violation_types?.length || 0} violation type(s)
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {!vehicleDetail && (
            <p className={styles.hint}>Search for a vehicle above to see its violation history across all cameras.</p>
          )}

          {vehicleDetail && (
            <>
              <div className={styles.summaryRow}>
                <div className={styles.summaryCard}>
                  <span className={styles.summaryVal}>{vehicleDetail.total_violations}</span>
                  <span className={styles.summaryLabel}>
                    Total Violations · {vehicleDetail.vehicle_plate || vehicleDetail.track_id}
                  </span>
                </div>
                <BreakdownPills breakdown={vehicleDetail.breakdown} />
              </div>

              <div className={styles.camerasSeen}>
                Seen at: {vehicleDetail.cameras_seen?.length
                  ? vehicleDetail.cameras_seen.join(', ')
                  : '—'}
              </div>

              <ViolationsTable
                violations={vehicleDetail.violations}
                onSelect={setSelected}
                showCameraCol={true}
              />
            </>
          )}
        </div>
      )}

      {selected && (
        <ViolationModal violation={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  )
}
