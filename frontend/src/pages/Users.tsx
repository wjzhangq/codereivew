import { useMemo, useState } from 'react'
import {
  Card,
  Tabs,
  Table,
  Tag,
  Button,
  Space,
  Modal,
  Form,
  Input,
  Select,
  Avatar,
  Typography,
  Alert,
  message,
} from 'antd'
import { UserAddOutlined, ReloadOutlined, MergeCellsOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  useUsers,
  useCreateUser,
  useUpdateUser,
  useIdentities,
  useResolveIdentities,
  useProjects,
} from '../hooks/api'

const { Text, Paragraph } = Typography

interface User {
  id: string
  username: string
  name: string
  role: 'admin' | 'user'
  projects?: string[]
  lastLogin?: string
  disabled?: boolean
}

interface Identity {
  id: string
  author: string
  email?: string
  platform?: string
  platformLogin?: string
  emails?: string[]
  verified: boolean
}

function avatarColor(seed: string) {
  const colors = ['#1677ff', '#52c41a', '#fa8c16', '#722ed1', '#eb2f96', '#13c2c2']
  let h = 0
  for (let i = 0; i < seed.length; i++) h = seed.charCodeAt(i) + ((h << 5) - h)
  return colors[Math.abs(h) % colors.length]
}

function AccountsTab() {
  const { data, isLoading } = useUsers()
  const createUser = useCreateUser()
  const updateUser = useUpdateUser()
  const { data: projects } = useProjects()
  const [modalOpen, setModalOpen] = useState(false)
  const [form] = Form.useForm()

  const users: User[] = useMemo(() => data ?? [], [data])
  const projectOptions = useMemo(
    () => (projects ?? []).map((p: any) => ({ label: p.name ?? p.id, value: p.id })),
    [projects],
  )

  const handleCreate = async () => {
    const values = await form.validateFields()
    createUser.mutate(values, {
      onSuccess: () => {
        message.success('用户已创建')
        setModalOpen(false)
        form.resetFields()
      },
      onError: () => message.error('创建失败'),
    })
  }

  const toggleDisabled = (u: User) => {
    updateUser.mutate(
      { id: u.id, disabled: !u.disabled },
      {
        onSuccess: () => message.success(u.disabled ? '已启用' : '已禁用'),
      },
    )
  }

  const columns: ColumnsType<User> = [
    {
      title: '用户',
      key: 'user',
      render: (_, row) => (
        <Space>
          <Avatar style={{ backgroundColor: avatarColor(row.username) }}>
            {row.name?.[0] ?? row.username[0]}
          </Avatar>
          <div>
            <div>{row.name || row.username}</div>
            <Text type="secondary" style={{ fontSize: 12 }}>
              @{row.username}
            </Text>
          </div>
        </Space>
      ),
    },
    {
      title: '角色',
      dataIndex: 'role',
      key: 'role',
      render: (role: string) =>
        role === 'admin' ? <Tag color="gold">管理员</Tag> : <Tag>成员</Tag>,
    },
    {
      title: '授权项目',
      dataIndex: 'projects',
      key: 'projects',
      render: (projects?: string[]) =>
        projects && projects.length > 0 ? (
          <Space size={4} wrap>
            {projects.map((p) => (
              <Tag key={p} color="blue">
                {p}
              </Tag>
            ))}
          </Space>
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
    {
      title: '最近登录',
      dataIndex: 'lastLogin',
      key: 'lastLogin',
      render: (v?: string) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {v ?? '从未'}
        </Text>
      ),
    },
    {
      title: '状态',
      dataIndex: 'disabled',
      key: 'disabled',
      render: (disabled?: boolean) =>
        disabled ? <Tag color="red">已禁用</Tag> : <Tag color="green">正常</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      render: (_, row) => (
        <Space>
          <Button
            size="small"
            danger={!row.disabled}
            onClick={() => toggleDisabled(row)}
            loading={updateUser.isPending}
          >
            {row.disabled ? '启用' : '禁用'}
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <>
      <div style={{ marginBottom: 16, textAlign: 'right' }}>
        <Button
          type="primary"
          icon={<UserAddOutlined />}
          onClick={() => setModalOpen(true)}
        >
          添加用户
        </Button>
      </div>
      <Table
        rowKey="id"
        loading={isLoading}
        columns={columns}
        dataSource={users}
        pagination={{ pageSize: 12, hideOnSinglePage: true }}
      />

      <Modal
        title="添加用户"
        open={modalOpen}
        onOk={handleCreate}
        confirmLoading={createUser.isPending}
        onCancel={() => setModalOpen(false)}
        destroyOnClose
      >
        <Form form={form} layout="vertical" initialValues={{ role: 'user' }}>
          <Form.Item
            name="username"
            label="用户名"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input placeholder="用于登录的唯一标识" />
          </Form.Item>
          <Form.Item
            name="password"
            label="初始密码"
            rules={[{ required: true, message: '请输入初始密码' }]}
          >
            <Input.Password placeholder="用户首次登录密码" />
          </Form.Item>
          <Form.Item name="name" label="显示名称">
            <Input placeholder="可选" />
          </Form.Item>
          <Form.Item name="role" label="角色">
            <Select
              options={[
                { label: '成员', value: 'user' },
                { label: '管理员', value: 'admin' },
              ]}
            />
          </Form.Item>
          <Form.Item name="projects" label="授权项目">
            <Select
              mode="multiple"
              allowClear
              placeholder="选择可访问的项目"
              options={projectOptions}
            />
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}

function IdentityTab() {
  const { data: projects } = useProjects()
  const projectId = projects?.[0]?.id
  const { data, isLoading } = useIdentities(projectId)
  const resolve = useResolveIdentities(projectId || "")

  const identities: Identity[] = useMemo(() => data ?? [], [data])

  const columns: ColumnsType<Identity> = [
    {
      title: '解析身份',
      key: 'author',
      render: (_, row) => (
        <Space>
          <Avatar size="small" style={{ backgroundColor: avatarColor(row.author) }}>
            {row.author?.[0]}
          </Avatar>
          <div>
            <div>{row.platformLogin || row.author}</div>
            {row.email && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                {row.email}
              </Text>
            )}
          </div>
        </Space>
      ),
    },
    {
      title: '平台',
      dataIndex: 'platform',
      key: 'platform',
      render: (p?: string) =>
        p ? <Tag color="blue">{p}</Tag> : <Text type="secondary">—</Text>,
    },
    {
      title: '关联邮箱',
      dataIndex: 'emails',
      key: 'emails',
      render: (emails?: string[]) =>
        emails && emails.length > 0 ? (
          <Space size={4} wrap>
            {emails.map((e) => (
              <Tag key={e} style={{ fontFamily: 'monospace', fontSize: 12 }}>
                {e}
              </Tag>
            ))}
          </Space>
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
    {
      title: '验证状态',
      dataIndex: 'verified',
      key: 'verified',
      render: (verified: boolean) =>
        verified ? (
          <Tag color="green">已验证</Tag>
        ) : (
          <Tag color="orange">未验证</Tag>
        ),
    },
    {
      title: '操作',
      key: 'action',
      render: () => (
        <Space>
          <Button size="small" icon={<MergeCellsOutlined />}>
            手动合并
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <>
      <div style={{ marginBottom: 16, textAlign: 'right' }}>
        <Button
          icon={<ReloadOutlined />}
          loading={resolve.isPending}
          disabled={!projectId}
          onClick={() =>
            resolve.mutate(undefined, {
              onSuccess: () => message.success('已重新解析身份'),
            })
          }
        >
          重新解析
        </Button>
      </div>
      <Table
        rowKey="id"
        loading={isLoading}
        columns={columns}
        dataSource={identities}
        pagination={{ pageSize: 12, hideOnSinglePage: true }}
      />
      <Alert
        style={{ marginTop: 16 }}
        type="info"
        showIcon
        message="身份解析说明"
        description={
          <Paragraph style={{ margin: 0 }}>
            系统优先通过平台 API 将提交作者匹配到平台账号。当无法匹配时,回退到 commit
            中的 git email,并标记为「未验证」。可手动合并同一开发者的多个身份。
          </Paragraph>
        }
      />
    </>
  )
}

export default function Users() {
  return (
    <div style={{ padding: 24 }}>
      <Card>
        <Tabs
          items={[
            { key: 'accounts', label: '账号', children: <AccountsTab /> },
            { key: 'identity', label: '身份解析映射', children: <IdentityTab /> },
          ]}
        />
      </Card>
    </div>
  )
}
