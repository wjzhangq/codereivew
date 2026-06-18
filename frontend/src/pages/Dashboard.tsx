import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Button,
  Card,
  Col,
  Alert,
  Input,
  Modal,
  Form,
  Row,
  Statistic,
  Tag,
  message,
} from 'antd'
import {
  PlusOutlined,
  DatabaseOutlined,
  SearchOutlined,
  ApartmentOutlined,
  BranchesOutlined,
  SafetyOutlined,
  InfoCircleOutlined,
  GithubOutlined,
} from '@ant-design/icons'
import { useProjects, useCreateProject } from '../hooks/api'
import { Health } from '../components/widgets'

function PlatformIcon({ p }: { p?: string }) {
  if (p === 'gitlab') return <span style={{ color: '#e2432a', fontWeight: 700, fontSize: 13 }}>GL</span>
  return <GithubOutlined style={{ fontSize: 14 }} />
}

function ProjectCard({ p, onOpen }: { p: any; onOpen: (id: string) => void }) {
  const indexing = p.status === 'indexing'
  return (
    <Card
      className="card-hover"
      styles={{ body: { padding: 0 } }}
      style={{ cursor: indexing ? 'default' : 'pointer', overflow: 'hidden' }}
      onClick={() => !indexing && onOpen(p.id)}
    >
      <div style={{ padding: '18px 20px 14px' }}>
        <div style={{ display: 'flex', gap: 12, marginBottom: 10, alignItems: 'flex-start' }}>
          <div
            style={{
              width: 40,
              height: 40,
              borderRadius: 10,
              background: 'var(--primary-bg)',
              color: 'var(--primary)',
              display: 'grid',
              placeItems: 'center',
              flexShrink: 0,
            }}
          >
            <DatabaseOutlined style={{ fontSize: 20 }} />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 650, fontSize: 15, color: 'var(--text)' }}>{p.name}</div>
            <div
              style={{
                fontSize: 12,
                color: 'var(--text-3)',
                marginTop: 2,
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}
            >
              <PlatformIcon p={p.platform} /> {p.org} · {p.lang}
            </div>
          </div>
          {p.health != null && <Health value={p.health} />}
        </div>
        <p
          style={{
            fontSize: 13,
            color: 'var(--text-2)',
            lineHeight: 1.6,
            margin: '0 0 14px',
            height: 42,
            overflow: 'hidden',
          }}
        >
          {p.desc}
        </p>
        {indexing ? (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
              <span style={{ fontSize: 12, color: 'var(--text-3)' }}>正在索引…</span>
              <span style={{ fontSize: 12, color: 'var(--text-3)' }}>{p.indexProgress}%</span>
            </div>
            <div style={{ height: 6, background: 'var(--fill-quaternary)', borderRadius: 3 }}>
              <div
                style={{
                  width: `${p.indexProgress}%`,
                  height: '100%',
                  background: 'var(--primary)',
                  borderRadius: 3,
                  transition: 'width .3s',
                }}
              />
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', gap: 18, fontSize: 13, color: 'var(--text-2)' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <ApartmentOutlined /> {p.modules ?? 0} 模块
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <BranchesOutlined /> {p.branches ?? 0} 分支
            </span>
            <span
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 5,
                color: p.openFindings > 8 ? 'var(--error)' : 'var(--text-2)',
              }}
            >
              <SafetyOutlined /> {p.openFindings ?? 0} 发现
            </span>
          </div>
        )}
      </div>
      <div
        style={{
          padding: '10px 20px',
          borderTop: '1px solid var(--border-2)',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}
      >
        <Tag color={indexing ? 'warning' : 'success'}>{indexing ? '索引中' : '已就绪'}</Tag>
        <span style={{ fontSize: 12, color: 'var(--text-3)', flex: 1, textAlign: 'right' }}>
          更新于 {p.lastIndexed ?? '—'}
        </span>
      </div>
    </Card>
  )
}

function detectPlatform(url: string): string {
  if (/gitlab/i.test(url)) return 'GitLab'
  return 'GitHub'
}

function AddRepoModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [form] = Form.useForm()
  const createProject = useCreateProject()
  const { data: projects = [] } = useProjects()
  const [duplicateError, setDuplicateError] = useState<string | null>(null)
  const [detectedPlatform, setDetectedPlatform] = useState<string>('')

  const handleUrlChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const url = e.target.value.trim()
    setDetectedPlatform(url ? detectPlatform(url) : '')
    const existing = (projects as any[]).find(
      (p) => p.git_url === url || p.repoUrl === url || p.gitUrl === url
    )
    if (existing) {
      setDuplicateError(`该仓库已由「${existing.name}」接入，如需访问请联系项目创建者申请权限。`)
    } else {
      setDuplicateError(null)
    }
  }

  const submit = async () => {
    if (duplicateError) return
    try {
      const values = await form.validateFields()
      await createProject.mutateAsync(values)
      message.success('已接入并开始索引')
      form.resetFields()
      setDuplicateError(null)
      setDetectedPlatform('')
      onClose()
    } catch (e: any) {
      if (e?.errorFields) return
      message.error('接入失败')
    }
  }

  const handleCancel = () => {
    form.resetFields()
    setDuplicateError(null)
    setDetectedPlatform('')
    onClose()
  }

  return (
    <Modal
      title="接入仓库"
      open={open}
      onCancel={handleCancel}
      width={520}
      onOk={submit}
      okText="接入并开始索引"
      okButtonProps={{ disabled: !!duplicateError }}
      cancelText="取消"
      confirmLoading={createProject.isPending}
      destroyOnClose
    >
      <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
        <Form.Item
          label="仓库地址"
          name="git_url"
          rules={[{ required: true, message: '请输入仓库地址' }]}
          extra={detectedPlatform ? `已识别平台：${detectedPlatform}` : undefined}
        >
          <Input
            placeholder="https://github.com/org/repo  或  git@github.com:org/repo.git"
            onChange={handleUrlChange}
            autoFocus
          />
        </Form.Item>
        {duplicateError && (
          <Alert
            type="warning"
            showIcon
            message={duplicateError}
            style={{ marginBottom: 16 }}
          />
        )}
        <Form.Item
          label="项目名称"
          name="name"
          rules={[{ required: true, message: '请输入项目名称' }]}
          extra="可随时修改，不影响仓库关联"
        >
          <Input placeholder="my-project" />
        </Form.Item>
        <Form.Item label="Deploy Key（只读，用于 clone 私有仓库）" name="deploy_key">
          <Input.TextArea
            rows={3}
            placeholder="-----BEGIN OPENSSH PRIVATE KEY-----"
            style={{ fontFamily: 'var(--mono)', fontSize: 12 }}
          />
        </Form.Item>
        <div
          style={{
            display: 'flex',
            gap: 10,
            padding: 12,
            background: 'var(--fill-quaternary)',
            borderRadius: 8,
          }}
        >
          <InfoCircleOutlined style={{ color: 'var(--text-3)', marginTop: 2 }} />
          <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
            默认分支将强制纳入并自动分析，其余分支可在项目详情页勾选。
          </span>
        </div>
      </Form>
    </Modal>
  )
}

export default function Dashboard() {
  const nav = useNavigate()
  const { data: projects = [] } = useProjects()
  const [q, setQ] = useState('')
  const [adding, setAdding] = useState(false)

  const list = useMemo(
    () =>
      projects.filter(
        (p: any) =>
          (p.name || '').includes(q) || (p.org || '').includes(q),
      ),
    [projects, q],
  )

  const totalFindings = projects.reduce((a: number, p: any) => a + (p.openFindings || 0), 0)
  const activeCount = projects.filter((p: any) => p.status === 'active').length
  const indexingCount = projects.filter((p: any) => p.status === 'indexing').length

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 650, margin: 0 }}>工作台</h1>
          <p style={{ color: 'var(--text-3)', margin: '4px 0 0' }}>
            已接入 {projects.length} 个仓库 · 持续自动化 Review
          </p>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setAdding(true)}>
          接入仓库
        </Button>
      </div>

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic title="接入仓库" value={projects.length} />
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }}>
              {activeCount} 个活跃 · {indexingCount} 个索引中
            </div>
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="本周已分析 Commit" value={128} />
            <div style={{ fontSize: 12, color: 'var(--success)', marginTop: 4 }}>较上周 +18%</div>
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="待处理安全发现" value={totalFindings} valueStyle={{ color: 'var(--error)' }} />
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }}>含严重/高危</div>
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="活跃分析" value={activeCount} />
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }}>持续索引中</div>
          </Card>
        </Col>
      </Row>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 16, fontWeight: 600 }}>我的项目</span>
          <Tag>{list.length}</Tag>
        </div>
        <Input
          prefix={<SearchOutlined />}
          placeholder="搜索仓库名 / 组织…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          style={{ width: 280 }}
          allowClear
        />
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))',
          gap: 16,
        }}
      >
        {list.map((p: any) => (
          <ProjectCard key={p.id} p={p} onOpen={(id) => nav(`/projects/${id}/overview`)} />
        ))}
        <Card
          onClick={() => setAdding(true)}
          style={{
            display: 'grid',
            placeItems: 'center',
            minHeight: 220,
            border: '1.5px dashed var(--border)',
            boxShadow: 'none',
            cursor: 'pointer',
            color: 'var(--text-3)',
          }}
        >
          <div style={{ textAlign: 'center' }}>
            <div
              style={{
                width: 48,
                height: 48,
                borderRadius: 12,
                background: 'var(--fill-quaternary)',
                display: 'grid',
                placeItems: 'center',
                margin: '0 auto 12px',
              }}
            >
              <PlusOutlined style={{ fontSize: 24 }} />
            </div>
            接入新仓库
          </div>
        </Card>
      </div>

      <AddRepoModal open={adding} onClose={() => setAdding(false)} />
    </div>
  )
}
