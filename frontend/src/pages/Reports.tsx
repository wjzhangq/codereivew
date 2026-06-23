import { useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Button, Card, DatePicker, Progress, Segmented, Space, Spin, Switch, Table, Tabs, Tag, Tooltip } from 'antd'
import {
  DownloadOutlined,
  CaretRightOutlined,
  CaretDownOutlined,
  WarningOutlined,
  FileMarkdownOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { useCommits, useContributors, useAnalyzeCommits, useWeeklyReport } from '../hooks/api'
import { Avatar, MiniBars } from '../components/widgets'
import { JobStatusEmpty } from '../components/JobStatusEmpty'

type Commit = {
  sha: string
  author: string
  authorAvatar?: string
  modules?: string[]
  additions?: number
  deletions?: number
  add?: number
  del?: number
  summary: string
  problem?: string
  approach?: string
  rawMessage?: string
  raw_message?: string
  messageDrift?: boolean
  message_drift?: boolean
}

type Contributor = {
  id: string
  name: string
  avatar?: string
  verified?: boolean
  commits: number
  additions?: number
  deletions?: number
  add?: number
  del?: number
  modules?: string[]
  focus?: string
}

const RANGE_OPTIONS = [
  { label: '近 30 天', value: '30d' },
  { label: '近 100 条', value: '100c' },
  { label: '自定义', value: 'custom' },
]

function CommitCard({ c }: { c: Commit }) {
  const [open, setOpen] = useState(false)
  const add = c.additions ?? c.add ?? 0
  const del = c.deletions ?? c.del ?? 0
  const raw = c.rawMessage ?? c.raw_message ?? ''
  const drift = c.messageDrift ?? c.message_drift ?? false
  return (
    <Card size="small" style={{ marginBottom: 12 }} styles={{ body: { padding: 16 } }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }} onClick={() => setOpen((v) => !v)}>
        {open ? <CaretDownOutlined /> : <CaretRightOutlined />}
        <Avatar name={c.author} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {c.summary}
          </div>
          <Space size={6} style={{ marginTop: 2 }}>
            <span className="mono" style={{ fontSize: 12, color: 'var(--text-3)' }}>{c.sha?.slice(0, 7)}</span>
            <span style={{ color: 'var(--success)', fontSize: 12 }}>+{add}</span>
            <span style={{ color: 'var(--error)', fontSize: 12 }}>-{del}</span>
            {(c.modules ?? []).map((m) => (
              <Tag key={m} style={{ marginInlineEnd: 0 }}>{m}</Tag>
            ))}
            {drift && (
              <Tag color="warning" icon={<WarningOutlined />} style={{ marginInlineEnd: 0 }}>
                文不对题
              </Tag>
            )}
          </Space>
        </div>
      </div>

      {open && (
        <div style={{ marginTop: 14 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div className="block-problem">
              <div style={{ fontWeight: 600, marginBottom: 6, color: 'var(--error)' }}>解决的问题</div>
              <div style={{ lineHeight: 1.6 }}>{c.problem || '—'}</div>
            </div>
            <div className="block-approach">
              <div style={{ fontWeight: 600, marginBottom: 6, color: 'var(--success)' }}>采用的思路</div>
              <div style={{ lineHeight: 1.6 }}>{c.approach || '—'}</div>
            </div>
          </div>
          {raw && (
            <div style={{ marginTop: 12, padding: '8px 12px', borderLeft: '3px solid var(--border)', background: 'var(--fill-quaternary, #fafafa)', color: 'var(--text-3)', fontSize: 13 }}>
              <span style={{ fontSize: 12, marginRight: 6 }}>原始 message(仅引用):</span>
              <span className="mono">{raw}</span>
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

function PeriodTab() {
  const { id = '' } = useParams()
  const [range, setRange] = useState('30d')
  const { data: commits = [], isLoading } = useCommits(id, range)
  const analyze = useAnalyzeCommits(id)

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Segmented options={RANGE_OPTIONS} value={range} onChange={(v) => setRange(v as string)} />
        <Button icon={<DownloadOutlined />}>导出</Button>
      </div>

      <Card
        style={{
          marginBottom: 16,
          background: 'linear-gradient(135deg, #eef2ff 0%, #f5f3ff 100%)',
          border: '1px solid var(--primary-border, #c7d2fe)',
        }}
        styles={{ body: { padding: 18 } }}
      >
        <div style={{ fontWeight: 600, marginBottom: 6 }}>本周期 AI 摘要</div>
        <div style={{ lineHeight: 1.7, color: 'var(--text-2)' }}>
          本周期共有 {(commits as Commit[]).length} 次提交。下方按提交逐条展示 LLM 对真实改动的理解
          （summary / 问题 / 思路），原始 commit message 仅作引用,不作为可信输入。
        </div>
      </Card>

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 40 }}>
          <Spin />
        </div>
      ) : (commits as Commit[]).length === 0 ? (
        <JobStatusEmpty
          project={id}
          types={['commit_analyze']}
          emptyText="本周期暂无已分析提交"
          triggerText="立即分析提交"
          onTrigger={() => analyze.mutate()}
          triggering={analyze.isPending}
        />
      ) : (
        (commits as Commit[]).map((c) => <CommitCard key={c.sha} c={c} />)
      )}
    </div>
  )
}

function ContribTab() {
  const { id = '' } = useParams()
  const [mode, setMode] = useState<'log' | 'blame'>('log')
  const { data, isLoading } = useContributors(id, mode)

  const list: Contributor[] = useMemo(() => {
    if (!data) return []
    return Array.isArray(data) ? data : (data.data ?? data.contributors ?? [])
  }, [data])

  const maxCommits = Math.max(1, ...list.map((c) => c.commits || 0))

  const columns: ColumnsType<Contributor> = [
    {
      title: '贡献者',
      dataIndex: 'name',
      render: (name: string, c) => (
        <Space>
          <Avatar name={name} />
          <span>{name}</span>
          <Tag color={c.verified ? 'success' : 'default'}>{c.verified ? '已验证' : '未验证'}</Tag>
        </Space>
      ),
    },
    {
      title: '活动量',
      dataIndex: 'commits',
      width: 220,
      render: (commits: number) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ flex: 1, height: 8, background: 'var(--border-2)', borderRadius: 4, overflow: 'hidden' }}>
            <div style={{ width: `${(commits / maxCommits) * 100}%`, height: '100%', background: 'var(--primary)' }} />
          </div>
          <span style={{ fontSize: 12, color: 'var(--text-3)', minWidth: 56 }}>{commits} commits</span>
        </div>
      ),
    },
    {
      title: '增删',
      key: 'churn',
      width: 130,
      render: (_v, c) => (
        <span>
          <span style={{ color: 'var(--success)' }}>+{c.additions ?? c.add ?? 0}</span>{' '}
          <span style={{ color: 'var(--error)' }}>-{c.deletions ?? c.del ?? 0}</span>
        </span>
      ),
    },
    {
      title: '主要模块',
      dataIndex: 'modules',
      render: (modules: string[] = []) => (
        <Space size={4} wrap>
          {modules.map((m) => (
            <Tag key={m} style={{ marginInlineEnd: 0 }}>{m}</Tag>
          ))}
        </Space>
      ),
    },
    {
      title: '工作重心',
      dataIndex: 'focus',
      render: (focus: string) => <span style={{ color: 'var(--text-2)' }}>{focus || '—'}</span>,
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Segmented
          options={[
            { label: 'by_log(谁改了什么)', value: 'log' },
            { label: 'by_blame(谁拥有代码)', value: 'blame' },
          ]}
          value={mode}
          onChange={(v) => setMode(v as 'log' | 'blame')}
        />
      </div>

      <Card size="small" style={{ marginBottom: 16 }} title="近 8 周趋势">
        <MiniBars data={[12, 18, 9, 22, 15, 27, 19, 24]} height={48} />
      </Card>

      <Card>
        <Table<Contributor>
          rowKey="id"
          loading={isLoading}
          columns={columns}
          dataSource={list}
          pagination={false}
          locale={{
            emptyText: (
              <JobStatusEmpty
                project={id}
                types={['contributor_report']}
                emptyText="暂无贡献数据(首次访问已自动入队,稍后刷新)"
              />
            ),
          }}
        />
        <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-3)' }}>
          身份解析:优先经平台 API 解析为平台账号;解析不到时回落 git email 并标记「未验证」。
        </div>
      </Card>
    </div>
  )
}

type WeeklyAuthor = {
  author: string
  commits: number
  categories: Record<string, number>
  filesChanged: number
  insertions: number
  deletions: number
  topDirs: string[]
  conventionalRatio: number
  qualityScore: number
  scope: string
  qualityNote: string
}

const CAT_COLOR: Record<string, string> = {
  feat: 'green', fix: 'red', refactor: 'blue', docs: 'cyan', test: 'purple',
  perf: 'gold', chore: 'default', ci: 'geekblue', build: 'geekblue',
  style: 'default', revert: 'volcano', other: 'default',
}

function qualityColor(score: number): string {
  if (score >= 85) return '#52c41a'
  if (score >= 70) return '#1677ff'
  if (score >= 55) return '#faad14'
  return '#ff4d4f'
}

function WeeklyAuthorCard({ a }: { a: WeeklyAuthor }) {
  return (
    <Card size="small" style={{ marginBottom: 12 }} styles={{ body: { padding: 16 } }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
        <Avatar name={a.author} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <span style={{ fontWeight: 600 }}>{a.author}</span>
            {Object.entries(a.categories).map(([k, v]) => (
              <Tag key={k} color={CAT_COLOR[k] ?? 'default'} style={{ marginInlineEnd: 0 }}>
                {k}×{v}
              </Tag>
            ))}
          </div>
          <div style={{ marginTop: 8, color: 'var(--text-2)', lineHeight: 1.7 }}>
            <b>功能范围：</b>{a.scope || '—'}
          </div>
          {a.qualityNote && (
            <div style={{ marginTop: 4, color: 'var(--text-2)', lineHeight: 1.7 }}>
              <b>质量点评：</b>{a.qualityNote}
            </div>
          )}
          <Space size={6} wrap style={{ marginTop: 8 }}>
            {a.topDirs.map((d) => (
              <Tag key={d} style={{ marginInlineEnd: 0 }}>{d}</Tag>
            ))}
          </Space>
          <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-3)' }}>
            {a.commits} 提交 · {a.filesChanged} 文件 ·{' '}
            <span style={{ color: 'var(--success)' }}>+{a.insertions}</span>{' '}
            <span style={{ color: 'var(--error)' }}>-{a.deletions}</span> · 规范率{' '}
            {Math.round(a.conventionalRatio * 100)}%
          </div>
        </div>
        <Tooltip title="质量分 = 提交规范度40 + 改动聚焦度30 + 体量合理度30">
          <Progress
            type="circle"
            size={56}
            percent={a.qualityScore}
            format={(p) => <span style={{ fontSize: 13 }}>{p}</span>}
            strokeColor={qualityColor(a.qualityScore)}
          />
        </Tooltip>
      </div>
    </Card>
  )
}

function WeeklyTab() {
  const { id = '' } = useParams()
  const [week, setWeek] = useState<string | undefined>(undefined)
  const [useLlm, setUseLlm] = useState(true)
  const { data, isLoading } = useWeeklyReport(id, { week, llm: useLlm })

  const authors: WeeklyAuthor[] = data?.authors ?? []
  const maxCommits = Math.max(1, ...authors.map((a) => a.commits || 0))

  const columns: ColumnsType<WeeklyAuthor> = [
    {
      title: '贡献者',
      dataIndex: 'author',
      render: (name: string) => (
        <Space><Avatar name={name} /><span>{name}</span></Space>
      ),
    },
    {
      title: '活动量',
      dataIndex: 'commits',
      width: 200,
      render: (commits: number) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ flex: 1, height: 8, background: 'var(--border-2)', borderRadius: 4, overflow: 'hidden' }}>
            <div style={{ width: `${(commits / maxCommits) * 100}%`, height: '100%', background: 'var(--primary)' }} />
          </div>
          <span style={{ fontSize: 12, color: 'var(--text-3)', minWidth: 56 }}>{commits} commits</span>
        </div>
      ),
    },
    {
      title: '类别',
      dataIndex: 'categories',
      render: (cats: Record<string, number>) => (
        <Space size={4} wrap>
          {Object.entries(cats).map(([k, v]) => (
            <Tag key={k} color={CAT_COLOR[k] ?? 'default'} style={{ marginInlineEnd: 0 }}>{k}×{v}</Tag>
          ))}
        </Space>
      ),
    },
    {
      title: '增删',
      key: 'churn',
      width: 120,
      render: (_v: any, a: WeeklyAuthor) => (
        <span>
          <span style={{ color: 'var(--success)' }}>+{a.insertions}</span>{' '}
          <span style={{ color: 'var(--error)' }}>-{a.deletions}</span>
        </span>
      ),
    },
    {
      title: '规范率',
      dataIndex: 'conventionalRatio',
      width: 80,
      render: (r: number) => <span>{Math.round(r * 100)}%</span>,
    },
    {
      title: '质量分',
      dataIndex: 'qualityScore',
      width: 90,
      sorter: (a: WeeklyAuthor, b: WeeklyAuthor) => a.qualityScore - b.qualityScore,
      render: (s: number) => (
        <span style={{ fontWeight: 600, color: qualityColor(s) }}>{s.toFixed(1)}</span>
      ),
    },
  ]

  const downloadMd = () => {
    if (!data?.markdown) return
    const blob = new Blob([data.markdown], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `weekly-${data.since}.md`
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, gap: 12, flexWrap: 'wrap' }}>
        <Space size={12} wrap>
          <DatePicker
            picker="week"
            placeholder="上一个完整周"
            onChange={(d) => setWeek(d ? d.format('YYYY-MM-DD') : undefined)}
          />
          <Space size={6}>
            <span style={{ fontSize: 13, color: 'var(--text-3)' }}>AI 描述</span>
            <Switch checked={useLlm} onChange={setUseLlm} size="small" />
          </Space>
        </Space>
        <Button icon={<DownloadOutlined />} onClick={downloadMd} disabled={!data?.markdown}>
          导出 Markdown
        </Button>
      </div>

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
      ) : authors.length === 0 ? (
        <Card><div style={{ textAlign: 'center', padding: 32, color: 'var(--text-3)' }}>
          <FileMarkdownOutlined style={{ fontSize: 28, marginBottom: 8 }} /><br />
          {data ? `${data.since} ~ ${data.until} 本周期无提交记录` : '暂无数据'}
        </div></Card>
      ) : (
        <>
          <Card
            style={{ marginBottom: 16, background: 'linear-gradient(135deg, #eef2ff 0%, #f5f3ff 100%)', border: '1px solid var(--primary-border, #c7d2fe)' }}
            styles={{ body: { padding: 18 } }}
          >
            <div style={{ fontWeight: 600, marginBottom: 6 }}>周期总览</div>
            <div style={{ color: 'var(--text-2)' }}>
              {data.since} ~ {data.until}　共 <b>{authors.length}</b> 位贡献者、
              <b>{data.totalCommits}</b> 次提交。质量分 = 提交规范度 + 改动聚焦度 + 体量合理度（满分 100，纯规则）。
            </div>
          </Card>

          <Card size="small" style={{ marginBottom: 16 }} title="汇总">
            <Table<WeeklyAuthor>
              rowKey="author"
              columns={columns}
              dataSource={authors}
              pagination={false}
              size="small"
            />
          </Card>

          <div style={{ fontWeight: 600, margin: '8px 0 12px' }}>明细</div>
          {authors.map((a) => <WeeklyAuthorCard key={a.author} a={a} />)}
        </>
      )}
    </div>
  )
}

export default function Reports() {
  return (
    <div className="fade-up">
      <h2 style={{ marginTop: 0, marginBottom: 16 }}>周期 / 贡献报告</h2>
      <Tabs
        items={[
          { key: 'weekly', label: '周报', children: <WeeklyTab /> },
          { key: 'period', label: '周期 / 功能理解', children: <PeriodTab /> },
          { key: 'contrib', label: '贡献汇总', children: <ContribTab /> },
        ]}
      />
    </div>
  )
}
