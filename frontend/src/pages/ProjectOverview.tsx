import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Button, Card, Checkbox, Col, Drawer, Row, Statistic, Tag, message } from 'antd'
import {
  DatabaseOutlined,
  ExportOutlined,
  ReloadOutlined,
  MessageOutlined,
  BranchesOutlined,
  ApartmentOutlined,
  FileOutlined,
  SafetyOutlined,
  AppstoreOutlined,
  InfoCircleOutlined,
  HistoryOutlined,
  BookOutlined,
  SyncOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import {
  useProject,
  useBranches,
  useSetWhitelist,
  useSyncRemote,
  useGraph,
  useReindex,
} from '../hooks/api'
import { Health, CatTag, CAT_COLOR, Avatar } from '../components/widgets'

// ── 模块依赖图谱 ───────────────────────────────────────────────
function ModuleGraph({
  modules,
  edges,
  onPick,
}: {
  modules: any[]
  edges: [string, string][]
  onPick: (m: any) => void
}) {
  const [focus, setFocus] = useState<string | null>(null)

  const adj = useMemo(() => {
    const m: Record<string, Set<string>> = {}
    modules.forEach((x) => (m[x.id] = new Set()))
    edges.forEach(([a, b]) => {
      m[a]?.add(b)
      m[b]?.add(a)
    })
    return m
  }, [modules, edges])

  const node = (id: string) => modules.find((m) => m.id === id)
  const hot = focus ? new Set([focus, ...(adj[focus] || [])]) : null
  const radius = (loc: number) => 20 + Math.sqrt(loc) / 4.2

  return (
    <div
      style={{
        position: 'relative',
        width: '100%',
        height: 560,
        background: 'radial-gradient(circle at 50% 42%, #fbfbfe 0%, #f6f7fb 70%)',
        borderRadius: 12,
        overflow: 'hidden',
      }}
    >
      <svg
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
      >
        {edges.map(([a, b], i) => {
          const A = node(a)
          const B = node(b)
          if (!A || !B) return null
          const on = hot && hot.has(a) && hot.has(b)
          const dim = hot && !on
          return (
            <line
              key={i}
              x1={A.x}
              y1={A.y}
              x2={B.x}
              y2={B.y}
              stroke={on ? 'var(--primary)' : '#d4d7e0'}
              strokeWidth={on ? 0.5 : 0.32}
              opacity={dim ? 0.18 : on ? 0.9 : 0.6}
              vectorEffect="non-scaling-stroke"
              style={{ transition: 'all .2s' }}
            />
          )
        })}
      </svg>

      {modules.map((m) => {
        const cc = CAT_COLOR[m.cat] || CAT_COLOR.core
        const isFocus = focus === m.id
        const on = hot && hot.has(m.id)
        const dim = hot && !on
        const d = radius(m.loc) * 2
        return (
          <div
            key={m.id}
            onMouseEnter={() => setFocus(m.id)}
            onMouseLeave={() => setFocus(null)}
            onClick={() => onPick(m)}
            style={{
              position: 'absolute',
              left: `${m.x}%`,
              top: `${m.y}%`,
              transform: 'translate(-50%,-50%)',
              width: d,
              height: d,
              borderRadius: '50%',
              cursor: 'pointer',
              zIndex: isFocus ? 5 : 2,
              background: '#fff',
              border: `2px solid ${cc.c}`,
              boxShadow: isFocus
                ? `0 8px 24px ${cc.c}40, 0 0 0 6px ${cc.bg}`
                : 'var(--shadow-1)',
              display: 'grid',
              placeItems: 'center',
              textAlign: 'center',
              padding: 6,
              opacity: dim ? 0.4 : 1,
              transition: 'all .2s',
              scale: isFocus ? '1.06' : '1',
            }}
          >
            <div>
              <div
                style={{
                  width: 26,
                  height: 26,
                  borderRadius: 7,
                  background: cc.bg,
                  color: cc.c,
                  display: 'grid',
                  placeItems: 'center',
                  margin: '0 auto 3px',
                }}
              >
                <AppstoreOutlined style={{ fontSize: 14 }} />
              </div>
              <div
                style={{
                  fontSize: 11,
                  fontWeight: 650,
                  lineHeight: 1.15,
                  color: 'var(--text)',
                  maxWidth: d - 14,
                }}
              >
                {m.name}
              </div>
              <div style={{ fontSize: 9.5, color: 'var(--text-3)', marginTop: 1 }}>
                {m.files} 文件 · {(m.loc / 1000).toFixed(1)}k
              </div>
            </div>
          </div>
        )
      })}

      <div
        style={{
          position: 'absolute',
          left: 14,
          bottom: 14,
          display: 'flex',
          gap: 14,
          flexWrap: 'wrap',
          background: 'rgba(255,255,255,.85)',
          backdropFilter: 'blur(4px)',
          padding: '8px 12px',
          borderRadius: 8,
          border: '1px solid var(--border-2)',
        }}
      >
        {Object.entries(CAT_COLOR).map(([k, v]) => (
          <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--text-2)' }}>
            <span style={{ width: 9, height: 9, borderRadius: '50%', background: v.c }} />
            {v.label}
          </div>
        ))}
      </div>
      <div
        style={{
          position: 'absolute',
          right: 14,
          top: 14,
          fontSize: 12,
          color: 'var(--text-3)',
          background: 'rgba(255,255,255,.85)',
          padding: '6px 10px',
          borderRadius: 8,
          border: '1px solid var(--border-2)',
        }}
      >
        社区检测 · 悬停查看爆炸半径 · 点击查看模块
      </div>
    </div>
  )
}

// ── 模块抽屉 ───────────────────────────────────────────────────
function ModuleDrawer({
  mod,
  edges,
  modules,
  onClose,
}: {
  mod: any
  edges: [string, string][]
  modules: any[]
  onClose: () => void
}) {
  const nav = useNavigate()
  const { id } = useParams()
  const cc = CAT_COLOR[mod.cat] || CAT_COLOR.core
  const deps = edges
    .filter(([a, b]) => a === mod.id || b === mod.id)
    .map(([a, b]) => (a === mod.id ? b : a))
  const depMods = deps.map((d) => modules.find((m) => m.id === d)).filter(Boolean)

  return (
    <Drawer
      open
      width={620}
      onClose={onClose}
      title={
        <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span
            style={{
              width: 30,
              height: 30,
              borderRadius: 8,
              background: cc.bg,
              color: cc.c,
              display: 'grid',
              placeItems: 'center',
            }}
          >
            <AppstoreOutlined />
          </span>
          {mod.name}
          <CatTag cat={mod.cat} />
        </span>
      }
    >
      <p style={{ color: 'var(--text-2)', lineHeight: 1.7, marginTop: 0 }}>{mod.desc}</p>

      <div style={{ display: 'flex', gap: 24, margin: '18px 0', alignItems: 'center' }}>
        <Health value={mod.health ?? null} size={56} />
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
            <span style={{ color: 'var(--text-3)' }}>文件 / 行数</span>
            <span>
              {mod.files} 文件 · {(mod.loc ?? 0).toLocaleString()} LOC
            </span>
          </div>
          {mod.owner && (
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
              <span style={{ color: 'var(--text-3)' }}>主要负责</span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <Avatar name={mod.owner} size={20} /> {mod.owner}
              </span>
            </div>
          )}
          {mod.churn && (
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
              <span style={{ color: 'var(--text-3)' }}>改动热度</span>
              <Tag color={mod.churn === 'high' ? 'error' : mod.churn === 'med' ? 'warning' : 'success'}>
                {mod.churn === 'high' ? '高频' : mod.churn === 'med' ? '中等' : '稳定'}
              </Tag>
            </div>
          )}
        </div>
      </div>

      <div style={{ borderTop: '1px solid var(--border-2)', margin: '8px 0 16px' }} />

      <div style={{ fontWeight: 600, marginBottom: 10, display: 'flex', alignItems: 'center', gap: 8 }}>
        <ApartmentOutlined /> 依赖模块(爆炸半径 {depMods.length})
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 18 }}>
        {depMods.length ? (
          depMods.map((n: any) => <Tag key={n.id}>{n.name}</Tag>)
        ) : (
          <span style={{ fontSize: 12, color: 'var(--text-3)' }}>无依赖关系。</span>
        )}
      </div>

      {mod.findings > 0 && (
        <>
          <div style={{ fontWeight: 600, margin: '18px 0 10px', display: 'flex', alignItems: 'center', gap: 8 }}>
            <SafetyOutlined /> 安全发现 {mod.findings}
          </div>
          <Button size="small" onClick={() => nav(`/projects/${id}/security`)}>
            查看安全面板
          </Button>
        </>
      )}

      <div style={{ display: 'flex', marginTop: 22, gap: 10 }}>
        <Button
          type="primary"
          icon={<MessageOutlined />}
          onClick={() => nav(`/projects/${id}/qa?q=${encodeURIComponent(`${mod.name} 模块是怎么实现的?`)}`)}
        >
          就该模块提问
        </Button>
        <Button icon={<BookOutlined />} onClick={() => nav(`/projects/${id}/wiki?page=${mod.id}`)}>
          查看 Wiki
        </Button>
      </div>
    </Drawer>
  )
}

// ── 分支白名单 ─────────────────────────────────────────────────
function BranchPanel({ projectId }: { projectId: string }) {
  const { data: branches = [] } = useBranches(projectId)
  const setWhitelist = useSetWhitelist(projectId)
  const syncRemote = useSyncRemote(projectId)
  const [syncError, setSyncError] = useState<string | null>(null)

  const whitelisted = branches.filter((b: any) => b.whitelisted).length

  const toggle = (b: any) => {
    if (b.isDefault) {
      message.info('默认分支强制纳入,不可取消')
      return
    }
    setWhitelist.mutate({ name: b.name, whitelisted: !b.whitelisted })
  }

  const doSync = () => {
    setSyncError(null)
    syncRemote.mutate(undefined, {
      onSuccess: () => message.success('已同步远程分支'),
      onError: (err: any) => {
        const msg = err?.response?.data?.detail ?? err?.message ?? '网络错误,无法连接远程仓库'
        setSyncError(msg)
      },
    })
  }

  return (
    <Card
      title={
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <BranchesOutlined /> 分支白名单
        </span>
      }
      extra={
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Tag>{whitelisted}/{branches.length} 已纳入</Tag>
          <Button
            size="small"
            icon={<SyncOutlined spin={syncRemote.isPending} />}
            loading={syncRemote.isPending}
            onClick={doSync}
          >
            同步远程
          </Button>
        </span>
      }
      styles={{ body: { padding: '6px 8px' } }}
    >
      {syncError && (
        <div
          style={{
            margin: '6px 8px 4px',
            padding: '8px 12px',
            borderRadius: 6,
            background: 'var(--error-bg, #fff2f0)',
            border: '1px solid var(--error-border, #ffccc7)',
            color: 'var(--error, #ff4d4f)',
            fontSize: 12,
            display: 'flex',
            gap: 8,
            alignItems: 'flex-start',
          }}
        >
          <WarningOutlined style={{ marginTop: 1, flexShrink: 0 }} />
          <span style={{ wordBreak: 'break-all' }}>{syncError}</span>
        </div>
      )}
      {branches.map((b: any) => (
        <div
          key={b.name}
          style={{ display: 'flex', gap: 10, padding: '10px 12px', borderRadius: 8, alignItems: 'flex-start' }}
        >
          <Checkbox checked={b.whitelisted} disabled={b.isDefault} onChange={() => toggle(b)} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
              <span className="mono" style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>
                {b.name}
              </span>
              {b.isDefault && <Tag color="processing">默认 · 强制</Tag>}
              {!b.indexed && b.whitelisted && <Tag color="warning">待索引</Tag>}
            </div>
            <div
              style={{
                fontSize: 12,
                color: 'var(--text-3)',
                marginTop: 2,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              <span className="mono">{(b.lastCommit || '').slice(0, 7)}</span> · {b.lastCommitMsg}
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 3, display: 'flex', alignItems: 'center', gap: 6 }}>
              {b.author && <Avatar name={b.author} size={18} />}
              {b.author} · {b.when}
              {(b.ahead > 0 || b.behind > 0) && (
                <span style={{ marginLeft: 4 }}>
                  ↑{b.ahead} ↓{b.behind}
                </span>
              )}
            </div>
          </div>
        </div>
      ))}
      <div style={{ padding: '10px 16px', borderTop: '1px solid var(--border-2)' }}>
        <div style={{ display: 'flex', gap: 6, alignItems: 'flex-start', fontSize: 12, color: 'var(--text-3)' }}>
          <InfoCircleOutlined style={{ marginTop: 2, flexShrink: 0 }} />
          默认分支强制纳入、不可取消;勾选其余分支后 webhook push 即触发自动分析。
        </div>
      </div>
    </Card>
  )
}

// ── 主页面 ─────────────────────────────────────────────────────
export default function ProjectOverview() {
  const { id = '' } = useParams()
  const nav = useNavigate()
  const { data: project } = useProject(id)
  const { data: branches = [] } = useBranches(id)
  const { data: graph } = useGraph(id)
  const reindex = useReindex(id)
  const [picked, setPicked] = useState<any>(null)

  const modules = graph?.modules || []
  const edges: [string, string][] = graph?.edges || []
  const whitelisted = branches.filter((b: any) => b.whitelisted).length
  const openFindings = modules.reduce((a: number, m: any) => a + (m.findings || 0), 0)

  const doReindex = async () => {
    await reindex.mutateAsync()
    message.success('已加入重新索引队列')
  }

  return (
    <div>
      {/* 项目头 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 18, flexWrap: 'wrap', gap: 12 }}>
        <div style={{ display: 'flex', gap: 14 }}>
          <div
            style={{
              width: 46,
              height: 46,
              borderRadius: 11,
              background: 'var(--primary-bg)',
              color: 'var(--primary)',
              display: 'grid',
              placeItems: 'center',
              flexShrink: 0,
            }}
          >
            <DatabaseOutlined style={{ fontSize: 24 }} />
          </div>
          <div>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
              <h1 style={{ fontSize: 22, fontWeight: 650, margin: 0, whiteSpace: 'nowrap' }}>
                {project?.name || id}
              </h1>
              {project?.version && <Tag>v{project.version}</Tag>}
              <Tag color="success">已就绪</Tag>
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', display: 'flex', gap: 10, marginTop: 4 }}>
              <span>{project?.org}</span>
              <span>·</span>
              <span>{project?.lang}</span>
              <span>·</span>
              <span>{project?.license}</span>
              <span>·</span>
              <span>更新于 {project?.lastIndexed ?? '—'}</span>
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <Button icon={<ExportOutlined />}>打开仓库</Button>
          <Button icon={<ReloadOutlined />} loading={reindex.isPending} onClick={doReindex}>
            重新索引
          </Button>
          <Button type="primary" icon={<MessageOutlined />} onClick={() => nav(`/projects/${id}/qa`)}>
            问答
          </Button>
        </div>
      </div>

      {/* 统计卡 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card>
            <Statistic title={<span><FileOutlined /> 源文件</span>} value={project?.files ?? 0} />
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }}>Tree-sitter 已解析</div>
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title={<span><ApartmentOutlined /> 模块(社区)</span>} value={modules.length} />
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }}>社区检测自动划分</div>
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title={<span><BranchesOutlined /> 白名单分支</span>} value={`${whitelisted}/${branches.length}`} />
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }}>默认分支强制纳入</div>
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title={<span><SafetyOutlined /> 待处理安全项</span>} value={openFindings} valueStyle={{ color: openFindings ? 'var(--error)' : undefined }} />
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }}>命中后 LLM 复审</div>
          </Card>
        </Col>
      </Row>

      {/* 主体两栏 */}
      <div style={{ display: 'grid', gridTemplateColumns: '340px 1fr', gap: 16, alignItems: 'start' }}>
        <BranchPanel projectId={id} />
        <Card
          title={
            <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <ApartmentOutlined /> 模块依赖图谱
            </span>
          }
          extra={
            <Button size="small" icon={<ReloadOutlined />}>
              重新布局
            </Button>
          }
          styles={{ body: { padding: 12 } }}
        >
          {modules.length ? (
            <ModuleGraph modules={modules} edges={edges} onPick={setPicked} />
          ) : (
            <div style={{ height: 560, display: 'grid', placeItems: 'center', color: 'var(--text-3)' }}>
              暂无图谱数据,索引完成后显示。
            </div>
          )}
        </Card>
      </div>

      {picked && (
        <ModuleDrawer mod={picked} edges={edges} modules={modules} onClose={() => setPicked(null)} />
      )}
    </div>
  )
}
