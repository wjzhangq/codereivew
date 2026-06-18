import { useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  App,
  Button,
  Card,
  Drawer,
  Segmented,
  Space,
  Table,
  Tag,
} from 'antd'
import {
  RightOutlined,
  SafetyCertificateOutlined,
  SyncOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { useFindings, useScan, useUpdateFinding } from '../hooks/api'
import { Sev, SEV } from '../components/widgets'
import { JobStatusEmpty } from '../components/JobStatusEmpty'

type Finding = {
  id: string
  severity: 'critical' | 'high' | 'medium' | 'low'
  title: string
  source: string
  rule: string
  file: string
  line: number
  module: string | null
  blastRadius?: number
  blast_radius?: number
  llmReviewed?: boolean
  llm_reviewed?: boolean
  status: 'open' | 'resolved' | 'ignored' | string
  evidence?: string
  suggestion?: string
}

const SEV_ORDER: Array<Finding['severity']> = ['critical', 'high', 'medium', 'low']

const STATUS_OPTIONS = [
  { label: '待处理', value: 'open' },
  { label: '已消除', value: 'resolved' },
  { label: '全部', value: 'all' },
]

export default function Security() {
  const { id = '' } = useParams()
  const { message } = App.useApp()
  const [status, setStatus] = useState<string>('open')
  const [sevFilter, setSevFilter] = useState<Finding['severity'] | null>(null)
  const [active, setActive] = useState<Finding | null>(null)

  const { data: findings = [], isLoading } = useFindings(id, status === 'all' ? undefined : status)
  const scan = useScan(id)
  const updateFinding = useUpdateFinding(id)

  const counts = useMemo(() => {
    const c: Record<string, number> = { critical: 0, high: 0, medium: 0, low: 0 }
    for (const f of findings as Finding[]) {
      if (c[f.severity] != null) c[f.severity] += 1
    }
    return c
  }, [findings])

  const rows = useMemo(() => {
    const list = findings as Finding[]
    return sevFilter ? list.filter((f) => f.severity === sevFilter) : list
  }, [findings, sevFilter])

  const blastOf = (f: Finding) => f.blastRadius ?? f.blast_radius ?? 0
  const isLlm = (f: Finding) => f.llmReviewed ?? f.llm_reviewed ?? false

  const runScan = async () => {
    try {
      await scan.mutateAsync()
      message.success('已触发扫描,稍后刷新查看结果')
    } catch {
      message.error('触发扫描失败')
    }
  }

  const setStatusOf = async (f: Finding, next: string) => {
    try {
      await updateFinding.mutateAsync({ fid: f.id, status: next })
      message.success(next === 'resolved' ? '已标记为处理' : '已忽略')
      setActive(null)
    } catch {
      message.error('操作失败')
    }
  }

  const columns: ColumnsType<Finding> = [
    {
      title: '等级',
      dataIndex: 'severity',
      width: 96,
      render: (s: Finding['severity']) => <Sev sev={s} />,
    },
    {
      title: '问题',
      dataIndex: 'title',
      render: (title: string, f) => (
        <Space size={8} wrap>
          <span style={{ fontWeight: 500 }}>{title}</span>
          {isLlm(f) && (
            <Tag color="purple" style={{ marginInlineEnd: 0 }}>
              LLM 复审
            </Tag>
          )}
          <span style={{ color: 'var(--text-3)', fontSize: 12 }}>{f.id}</span>
        </Space>
      ),
    },
    {
      title: '来源 / 规则',
      dataIndex: 'rule',
      width: 200,
      render: (rule: string, f) => (
        <div style={{ lineHeight: 1.4 }}>
          <div style={{ fontSize: 13 }}>{f.source}</div>
          <div style={{ fontSize: 12, color: 'var(--text-3)' }}>{rule}</div>
        </div>
      ),
    },
    {
      title: '文件',
      dataIndex: 'file',
      width: 220,
      ellipsis: true,
      render: (file: string, f) => (
        <span className="mono" style={{ fontSize: 12 }}>
          {file}
          {f.line ? `:${f.line}` : ''}
        </span>
      ),
    },
    {
      title: '模块',
      dataIndex: 'module',
      width: 140,
      render: (m: string | null) => (m ? <Tag>{m}</Tag> : <span style={{ color: 'var(--text-4)' }}>—</span>),
    },
    {
      title: '爆炸半径',
      key: 'blast',
      width: 100,
      render: (_v, f) => <span>{blastOf(f)} 处</span>,
    },
    {
      title: '',
      key: 'arrow',
      width: 40,
      render: () => <RightOutlined style={{ color: 'var(--text-4)' }} />,
    },
  ]

  return (
    <div className="fade-up">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>安全面板</h2>
        <Space>
          <Button icon={<SyncOutlined />}>对比基线</Button>
          <Button type="primary" icon={<SafetyCertificateOutlined />} loading={scan.isPending} onClick={runScan}>
            立即扫描
          </Button>
        </Space>
      </div>

      {/* 4 severity count filter cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 16 }}>
        {SEV_ORDER.map((sev) => {
          const meta = SEV[sev]
          const selected = sevFilter === sev
          return (
            <Card
              key={sev}
              size="small"
              hoverable
              onClick={() => setSevFilter(selected ? null : sev)}
              style={{
                cursor: 'pointer',
                borderColor: selected ? meta.c : undefined,
                boxShadow: selected ? `0 0 0 2px ${meta.c}33` : undefined,
              }}
              styles={{ body: { padding: 16 } }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: meta.c, fontSize: 13 }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: meta.c }} />
                {meta.label}
              </div>
              <div style={{ fontSize: 28, fontWeight: 680, marginTop: 6 }}>{counts[sev] ?? 0}</div>
            </Card>
          )
        })}
      </div>

      <Card
        styles={{ body: { paddingTop: 12 } }}
        title={
          <Segmented
            options={STATUS_OPTIONS}
            value={status}
            onChange={(v) => setStatus(v as string)}
          />
        }
      >
        <Table<Finding>
          rowKey="id"
          loading={isLoading}
          columns={columns}
          dataSource={rows}
          pagination={{ pageSize: 12, hideOnSinglePage: true }}
          onRow={(record) => ({ onClick: () => setActive(record), style: { cursor: 'pointer' } })}
          locale={{
            emptyText: (
              <JobStatusEmpty
                project={id}
                types={['security_scan']}
                emptyText="暂无安全发现"
                triggerText="立即扫描"
                onTrigger={runScan}
                triggering={scan.isPending}
              />
            ),
          }}
        />
      </Card>

      <Drawer
        width={480}
        open={!!active}
        onClose={() => setActive(null)}
        title={
          active && (
            <Space>
              <Sev sev={active.severity} />
              <span style={{ color: 'var(--text-3)', fontSize: 13 }}>{active.id}</span>
              <Tag>{active.status === 'resolved' ? '已消除' : active.status === 'ignored' ? '已忽略' : '待处理'}</Tag>
            </Space>
          )
        }
        footer={
          active && (
            <Space>
              <Button type="primary" onClick={() => setStatusOf(active, 'resolved')}>
                标记已处理
              </Button>
              <Button onClick={() => setStatusOf(active, 'ignored')}>忽略此规则</Button>
              <Button type="link">在仓库查看</Button>
            </Space>
          )
        }
      >
        {active && (
          <div>
            <h3 style={{ marginTop: 0 }}>{active.title}</h3>
            <Space size={8} wrap style={{ marginBottom: 16 }}>
              <Tag>{active.source}</Tag>
              <Tag color="geekblue">{active.rule}</Tag>
              {active.module && <Tag>{active.module}</Tag>}
              {isLlm(active) && <Tag color="purple">LLM 复审</Tag>}
            </Space>

            <div style={{ marginBottom: 16 }}>
              <div style={{ color: 'var(--text-3)', fontSize: 12, marginBottom: 4 }}>文件位置</div>
              <span className="mono">
                {active.file}
                {active.line ? `:${active.line}` : ''}
              </span>
            </div>

            <div style={{ marginBottom: 16 }}>
              <div style={{ color: 'var(--text-3)', fontSize: 12, marginBottom: 4 }}>爆炸半径</div>
              <span>{blastOf(active)} 处受影响</span>
            </div>

            {active.evidence && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ color: 'var(--text-3)', fontSize: 12, marginBottom: 6 }}>命中证据</div>
                <pre className="code-block" style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
                  {active.evidence}
                </pre>
              </div>
            )}

            {active.suggestion && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ color: 'var(--text-3)', fontSize: 12, marginBottom: 6 }}>修复建议</div>
                <div style={{ background: 'var(--primary-bg)', padding: '12px 14px', borderRadius: 8, lineHeight: 1.6 }}>
                  {active.suggestion}
                </div>
              </div>
            )}
          </div>
        )}
      </Drawer>
    </div>
  )
}
