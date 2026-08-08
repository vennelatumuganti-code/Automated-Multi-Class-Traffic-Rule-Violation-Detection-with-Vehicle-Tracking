import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import styles from './ViolationChart.module.css'

const COLORS = { no_helmet: '#C81E3A', triple_riding: '#B8860B', signal_jump: '#C81E3A' }
const LABELS = { no_helmet: 'No Helmet', triple_riding: 'Triple Riding', signal_jump: 'Signal Jump' }

export default function ViolationChart({ summary = {} }) {
  const data = Object.entries(summary).map(([key, count]) => ({
    name:  LABELS[key] || key,
    count,
    color: COLORS[key] || '#1A1A1A',
  }))

  if (data.length === 0) return (
    <div className={styles.empty}>Violation breakdown will appear after analysis.</div>
  )

  return (
    <div className={styles.wrap}>
      <div className={styles.hdr}>Violation Breakdown</div>
      <ResponsiveContainer width="100%" height={120}>
        <BarChart data={data} barSize={28} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
          <XAxis dataKey="name" tick={{ fill: '#6B7280', fontSize: 11, fontFamily: 'Syne' }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fill: '#6B7280', fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
          <Tooltip
            cursor={{ fill: 'rgba(26,26,26,0.04)' }}
            contentStyle={{ background: '#FFFFFF', border: '1px solid rgba(0,0,0,0.10)', borderRadius: 8, color: '#1A1A1A', fontFamily: 'Syne', boxShadow: '0 4px 16px rgba(0,0,0,0.08)' }}
          />
          <Bar dataKey="count" radius={[4,4,0,0]}>
            {data.map((d, i) => <Cell key={i} fill={d.color} fillOpacity={0.9} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
