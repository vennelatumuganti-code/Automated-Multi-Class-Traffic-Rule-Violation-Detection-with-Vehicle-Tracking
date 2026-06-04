import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import styles from './ViolationChart.module.css'

const COLORS = { no_helmet: '#FF4C4C', triple_riding: '#FFD166', signal_jump: '#FF4C4C' }
const LABELS = { no_helmet: 'No Helmet', triple_riding: 'Triple Riding', signal_jump: 'Signal Jump' }

export default function ViolationChart({ summary = {} }) {
  const data = Object.entries(summary).map(([key, count]) => ({
    name:  LABELS[key] || key,
    count,
    color: COLORS[key] || '#00E5C3',
  }))

  if (data.length === 0) return (
    <div className={styles.empty}>Violation breakdown will appear after analysis.</div>
  )

  return (
    <div className={styles.wrap}>
      <div className={styles.hdr}>Violation Breakdown</div>
      <ResponsiveContainer width="100%" height={120}>
        <BarChart data={data} barSize={28} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
          <XAxis dataKey="name" tick={{ fill: '#7DA4C9', fontSize: 11, fontFamily: 'Syne' }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fill: '#7DA4C9', fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
          <Tooltip
            cursor={{ fill: 'rgba(0,229,195,0.05)' }}
            contentStyle={{ background: '#162E55', border: '1px solid rgba(0,229,195,0.15)', borderRadius: 8, color: '#E8F4FF', fontFamily: 'Syne' }}
          />
          <Bar dataKey="count" radius={[4,4,0,0]}>
            {data.map((d, i) => <Cell key={i} fill={d.color} fillOpacity={0.85} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
