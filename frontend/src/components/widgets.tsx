/* components/widgets.tsx — AntD 未覆盖的自封装组件 */
import { Tag } from 'antd'

export const CAT_COLOR: Record<string, { c: string; bg: string; label: string }> = {
  core: { c: '#4f46e5', bg: '#eef2ff', label: '核心' },
  infra: { c: '#0891b2', bg: '#ecfeff', label: '基础设施' },
  api: { c: '#7c3aed', bg: '#f5f3ff', label: '接口' },
  feature: { c: '#d97706', bg: '#fffbeb', label: '功能' },
}
export const SEV: Record<string, { c: string; bg: string; label: string }> = {
  critical: { c: '#dc2626', bg: '#fef2f2', label: '严重' },
  high: { c: '#ea580c', bg: '#fff7ed', label: '高危' },
  medium: { c: '#d97706', bg: '#fffbeb', label: '中危' },
  low: { c: '#0891b2', bg: '#ecfeff', label: '低危' },
}

export function Health({ value, size = 36 }: { value: number | null; size?: number }) {
  if (value == null) return <span className="hint">—</span>
  const c = value >= 85 ? '#16a34a' : value >= 70 ? '#d97706' : '#dc2626'
  const sw = 4, r = (size - sw) / 2, circ = 2 * Math.PI * r
  return (
    <div style={{ position: 'relative', width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="var(--border-2)" strokeWidth={sw}/>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={c} strokeWidth={sw} strokeLinecap="round"
          strokeDasharray={circ} strokeDashoffset={circ*(1-value/100)} style={{transition:'stroke-dashoffset .6s'}}/>
      </svg>
      <span style={{position:'absolute',inset:0,display:'grid',placeItems:'center',fontSize:size*0.3,fontWeight:700,color:c}}>{value}</span>
    </div>
  )
}

export function Sev({ sev }: { sev: string }) {
  const s = SEV[sev] || SEV.low
  return <span style={{color:s.c,display:'inline-flex',alignItems:'center',gap:6,fontWeight:500}}>
    <span style={{width:7,height:7,borderRadius:'50%',background:s.c}}/>{s.label}
  </span>
}

export function MiniBars({ data, color='var(--primary)', height=40 }: { data: number[]; color?: string; height?: number }) {
  const max = Math.max(...data, 1)
  return <div style={{display:'flex',alignItems:'flex-end',gap:3,height}}>
    {data.map((v,i)=><div key={i} style={{flex:1,height:Math.max(2,(v/max)*height),background:color,borderRadius:2,opacity:.35+.65*(v/max)}}/>)}
  </div>
}

export function CatTag({ cat }: { cat: string }) {
  const cc = CAT_COLOR[cat] || CAT_COLOR.core
  return <Tag style={{color:cc.c,background:cc.bg,border:`1px solid ${cc.c}33`}}>{cc.label}</Tag>
}

export function Avatar({ name, color = '#4f46e5', size = 28 }: { name: string; color?: string; size?: number }) {
  return <span style={{width:size,height:size,borderRadius:6,background:color,color:'#fff',display:'inline-grid',placeItems:'center',fontSize:size*0.4,fontWeight:600,flexShrink:0}}>
    {name.slice(0,2).toUpperCase()}
  </span>
}
