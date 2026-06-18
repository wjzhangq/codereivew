/* components/JobStatusEmpty.tsx — 把空面板与背后的队列任务状态关联起来

   空数据不再只显示「暂无」,而是据最近一条相关 job 区分三态:
     · 无任务   → 提示去触发(可带触发按钮)
     · 运行中/排队 → 进度 + 轮询提示
     · 失败     → 红色告警 + 失败原因 + 重试
*/
import { Empty, Spin, Alert, Button, Space, Progress, Typography } from 'antd'
import { RedoOutlined, SyncOutlined } from '@ant-design/icons'
import { useLatestJob, useRetryJob } from '../hooks/api'

const { Text } = Typography

export function JobStatusEmpty({
  project,
  types,
  emptyText = '暂无数据',
  triggerText,
  onTrigger,
  triggering,
}: {
  project: string
  types: string[]
  emptyText?: string
  triggerText?: string
  onTrigger?: () => void
  triggering?: boolean
}) {
  const { data: job, isLoading } = useLatestJob(project, types)
  const retry = useRetryJob()

  if (isLoading) {
    return (
      <div style={{ padding: 48, textAlign: 'center' }}>
        <Spin />
      </div>
    )
  }

  // 运行中 / 排队中
  if (job && (job.status === 'running' || job.status === 'queued')) {
    const running = job.status === 'running'
    return (
      <div style={{ padding: 40, textAlign: 'center' }}>
        <Space direction="vertical" size={12} style={{ width: 360, maxWidth: '100%' }}>
          <Space>
            <SyncOutlined spin={running} />
            <Text>{running ? '任务执行中,完成后自动刷新…' : '任务排队中,等待 Worker 领取…'}</Text>
          </Space>
          {running && <Progress percent={job.progress ?? 0} status="active" />}
          {job.detail && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              {job.detail}
            </Text>
          )}
          <Text type="secondary" style={{ fontSize: 12 }}>
            {job.id}
          </Text>
        </Space>
      </div>
    )
  }

  // 失败(含零产出)
  if (job && job.status === 'failed') {
    return (
      <div style={{ padding: 24 }}>
        <Alert
          type="error"
          showIcon
          message={`任务执行失败(${job.id})`}
          description={
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <pre style={{ whiteSpace: 'pre-wrap', margin: 0, fontSize: 13 }}>
                {job.error || '执行成功但无任何产出'}
              </pre>
              <Button
                size="small"
                icon={<RedoOutlined />}
                loading={retry.isPending}
                onClick={() => retry.mutate(job.id)}
              >
                重试
              </Button>
            </Space>
          }
        />
      </div>
    )
  }

  // 无相关任务(或上次已完成但确无数据)→ 引导触发
  return (
    <div style={{ padding: 40 }}>
      <Empty description={emptyText}>
        {triggerText && onTrigger && (
          <Button type="primary" loading={triggering} onClick={onTrigger}>
            {triggerText}
          </Button>
        )}
      </Empty>
    </div>
  )
}
