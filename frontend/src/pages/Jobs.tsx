import { useMemo, useState } from 'react'
import {
  Card,
  Table,
  Tag,
  Button,
  Segmented,
  Progress,
  Spin,
  Space,
  Badge,
  Typography,
  Row,
  Col,
  Statistic,
} from 'antd'
import { ReloadOutlined, RedoOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { useJobs, useRetryJob } from '../hooks/api'

const { Title, Text, Paragraph } = Typography

type JobStatus = 'running' | 'queued' | 'done' | 'failed'

interface Job {
  id: string
  type: string
  project: string
  branch?: string
  priority: 'high' | 'medium' | 'low'
  status: JobStatus
  progress?: number
  worker?: string | null
  detail?: string
  updatedAt?: string
  finishedAt?: string
}

const TYPE_COLOR: Record<string, string> = {
  fetch: 'blue',
  index_build: 'geekblue',
  index_incremental: 'cyan',
  commit_analyze: 'purple',
  security_scan: 'red',
  contributor_report: 'gold',
  wiki_gen: 'green',
}

const TYPE_LABEL: Record<string, string> = {
  fetch: '拉取',
  index_build: '全量索引',
  index_incremental: '增量索引',
  commit_analyze: '提交分析',
  security_scan: '安全扫描',
  contributor_report: '贡献统计',
  wiki_gen: 'Wiki 生成',
}

const PRIORITY_META: Record<string, { color: string; label: string }> = {
  high: { color: 'red', label: '高' },
  medium: { color: 'orange', label: '中' },
  low: { color: 'default', label: '低' },
}

const STATUS_META: Record<JobStatus, { color: string; label: string }> = {
  running: { color: 'processing', label: '运行中' },
  queued: { color: 'default', label: '排队中' },
  done: { color: 'success', label: '已完成' },
  failed: { color: 'error', label: '失败' },
}

const CLAIM_SQL = `BEGIN IMMEDIATE;

UPDATE jobs
SET status = 'running',
    worker = :worker_id,
    started_at = CURRENT_TIMESTAMP
WHERE id = (
  SELECT id FROM jobs
  WHERE status = 'queued'
    AND scheduled_at <= CURRENT_TIMESTAMP
  ORDER BY priority DESC, id ASC
  LIMIT 1
)
RETURNING id, type, project, branch, payload;

COMMIT;`

export default function Jobs() {
  const [filter, setFilter] = useState<'all' | JobStatus>('all')
  const { data, isLoading, refetch, isFetching } = useJobs()
  const retry = useRetryJob()

  const jobs: Job[] = useMemo(() => data ?? [], [data])

  const stats = useMemo(() => {
    const running = jobs.filter((j) => j.status === 'running').length
    const queued = jobs.filter((j) => j.status === 'queued').length
    const done = jobs.filter((j) => j.status === 'done').length
    const failed = jobs.filter((j) => j.status === 'failed').length
    return { running, queued, done, failed }
  }, [jobs])

  const workers = useMemo(() => {
    const set = new Set<string>()
    jobs.forEach((j) => {
      if (j.status === 'running' && j.worker) set.add(j.worker)
    })
    return Array.from(set)
  }, [jobs])

  const filtered = useMemo(
    () => (filter === 'all' ? jobs : jobs.filter((j) => j.status === filter)),
    [jobs, filter],
  )

  const columns: ColumnsType<Job> = [
    {
      title: '任务',
      dataIndex: 'id',
      key: 'id',
      render: (id: string, row) => (
        <div>
          <Text strong style={{ fontFamily: 'monospace' }}>
            {id}
          </Text>
          {row.detail && (
            <div>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {row.detail}
              </Text>
            </div>
          )}
        </div>
      ),
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      render: (type: string) => (
        <Tag color={TYPE_COLOR[type] ?? 'default'}>{TYPE_LABEL[type] ?? type}</Tag>
      ),
    },
    {
      title: '项目 / 分支',
      key: 'project',
      render: (_, row) => (
        <div>
          <div>{row.project}</div>
          {row.branch && (
            <Text type="secondary" style={{ fontSize: 12, fontFamily: 'monospace' }}>
              {row.branch}
            </Text>
          )}
        </div>
      ),
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      key: 'priority',
      render: (p: string) => {
        const meta = PRIORITY_META[p] ?? PRIORITY_META.low
        return <Tag color={meta.color}>{meta.label}</Tag>
      },
    },
    {
      title: '状态 / 进度',
      key: 'status',
      width: 220,
      render: (_, row) => {
        const meta = STATUS_META[row.status]
        if (row.status === 'running') {
          return (
            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              <Space size={6}>
                <Spin size="small" />
                <Tag color={meta.color}>{meta.label}</Tag>
              </Space>
              <Progress percent={row.progress ?? 0} size="small" status="active" />
            </Space>
          )
        }
        return <Tag color={meta.color}>{meta.label}</Tag>
      },
    },
    {
      title: 'Worker',
      dataIndex: 'worker',
      key: 'worker',
      render: (w?: string | null) =>
        w ? (
          <Text style={{ fontFamily: 'monospace', fontSize: 12 }}>{w}</Text>
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
    {
      title: '时间',
      key: 'time',
      render: (_, row) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {row.finishedAt ?? row.updatedAt ?? '—'}
        </Text>
      ),
    },
    {
      title: '',
      key: 'action',
      width: 90,
      render: (_, row) =>
        row.status === 'failed' ? (
          <Button
            size="small"
            icon={<RedoOutlined />}
            loading={retry.isPending}
            onClick={() => retry.mutate(row.id)}
          >
            重试
          </Button>
        ) : null,
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <Row align="middle" justify="space-between" style={{ marginBottom: 20 }}>
        <Col>
          <Title level={3} style={{ margin: 0 }}>
            任务中心
          </Title>
        </Col>
        <Col>
          <Space size={16}>
            <Space size={8}>
              <Badge status="success" />
              <Text type="secondary">
                {workers.length > 0 ? `${workers.length} 个 Worker 在线` : '无活跃 Worker'}
              </Text>
              {workers.map((w) => (
                <Tag key={w} color="green" style={{ fontFamily: 'monospace' }}>
                  {w}
                </Tag>
              ))}
            </Space>
            <Button
              icon={<ReloadOutlined />}
              loading={isFetching}
              onClick={() => refetch()}
            >
              刷新
            </Button>
          </Space>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginBottom: 20 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="运行中"
              value={stats.running}
              valueStyle={{ color: '#1677ff' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="排队中" value={stats.queued} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="今日完成"
              value={stats.done}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="失败重试"
              value={stats.failed}
              valueStyle={{ color: stats.failed > 0 ? '#ff4d4f' : undefined }}
            />
          </Card>
        </Col>
      </Row>

      <Card
        style={{ marginBottom: 20 }}
        title={
          <Segmented
            value={filter}
            onChange={(v) => setFilter(v as typeof filter)}
            options={[
              { label: '全部', value: 'all' },
              { label: '运行中', value: 'running' },
              { label: '排队', value: 'queued' },
              { label: '失败', value: 'failed' },
            ]}
          />
        }
      >
        <Table
          rowKey="id"
          loading={isLoading}
          columns={columns}
          dataSource={filtered}
          pagination={{ pageSize: 12, hideOnSinglePage: true }}
        />
      </Card>

      <Card title="原子领取 SQL (SQLite claim 队列)">
        <Paragraph type="secondary" style={{ marginBottom: 12 }}>
          Worker 使用 <Text code>BEGIN IMMEDIATE</Text> +{' '}
          <Text code>RETURNING</Text> 原子领取下一个排队任务,按优先级与入队顺序出队,避免多
          Worker 抢占同一任务。
        </Paragraph>
        <pre
          style={{
            background: '#1e1e1e',
            color: '#d4d4d4',
            padding: 16,
            borderRadius: 8,
            overflowX: 'auto',
            fontSize: 13,
            lineHeight: 1.6,
            margin: 0,
          }}
        >
          <code>{CLAIM_SQL}</code>
        </pre>
      </Card>
    </div>
  )
}
