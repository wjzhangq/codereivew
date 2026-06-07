import { useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  Card,
  Menu,
  Input,
  Button,
  Switch,
  Segmented,
  Tag,
  Table,
  Modal,
  Form,
  Space,
  Typography,
  message,
} from 'antd'
import {
  CloudUploadOutlined,
  ApiOutlined,
  KeyOutlined,
  SettingOutlined,
  GithubOutlined,
  CopyOutlined,
  PlusOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  useProjectSettings,
  useCreateKey,
  useRevokeKey,
} from '../hooks/api'

const { Text, Title, Paragraph } = Typography

type Section =
  | 'repo'
  | 'webhook'
  | 'apikey'
  | 'platform'
  | 'analysis'

function CopyField({ value }: { value: string }) {
  return (
    <Input
      readOnly
      value={value}
      style={{ fontFamily: 'monospace', fontSize: 13 }}
      addonAfter={
        <CopyOutlined
          style={{ cursor: 'pointer' }}
          onClick={() => {
            navigator.clipboard?.writeText(value)
            message.success('已复制')
          }}
        />
      }
    />
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '130px 1fr',
        gap: 16,
        alignItems: 'center',
        marginBottom: 20,
      }}
    >
      <Text type="secondary">{label}</Text>
      <div>{children}</div>
    </div>
  )
}

function SectionHeader({ title, desc }: { title: string; desc?: string }) {
  return (
    <div style={{ marginBottom: 24 }}>
      <Title level={5} style={{ margin: 0 }}>
        {title}
      </Title>
      {desc && (
        <Text type="secondary" style={{ fontSize: 13 }}>
          {desc}
        </Text>
      )}
    </div>
  )
}

export default function Settings() {
  const { id: projectId = '' } = useParams()
  const [section, setSection] = useState<Section>('repo')
  const { data, isLoading } = useProjectSettings(projectId)
  const createKey = useCreateKey(projectId)
  const revokeKey = useRevokeKey(projectId)

  const [keyModalOpen, setKeyModalOpen] = useState(false)
  const [keyForm] = Form.useForm()
  const [createdKey, setCreatedKey] = useState<string | null>(null)

  const settings = data ?? {}
  const keys = useMemo(() => settings.apiKeys ?? settings.keys ?? [], [settings])

  const webhookUrl = `${window.location.origin}/api/webhook/${projectId}`

  const handleCreateKey = async () => {
    const values = await keyForm.validateFields()
    createKey.mutate(values, {
      onSuccess: (res: any) => {
        message.success('API Key 已创建')
        setCreatedKey(res?.key ?? res?.token ?? null)
        keyForm.resetFields()
      },
      onError: () => message.error('创建失败'),
    })
  }

  const keyColumns: ColumnsType<any> = [
    { title: '名称', dataIndex: 'name', key: 'name' },
    {
      title: '前缀',
      dataIndex: 'prefix',
      key: 'prefix',
      render: (v: string) => <Text code>{v ?? '—'}</Text>,
    },
    { title: '创建时间', dataIndex: 'createdAt', key: 'createdAt' },
    {
      title: '操作',
      key: 'action',
      render: (_, row) => (
        <Button
          size="small"
          danger
          loading={revokeKey.isPending}
          onClick={() =>
            revokeKey.mutate(row.id, {
              onSuccess: () => message.success('已吊销'),
            })
          }
        >
          吊销
        </Button>
      ),
    },
  ]

  const menuItems = [
    { key: 'repo', icon: <CloudUploadOutlined />, label: '仓库接入' },
    { key: 'webhook', icon: <ApiOutlined />, label: 'Webhook' },
    { key: 'apikey', icon: <KeyOutlined />, label: 'API Key' },
    { key: 'platform', icon: <GithubOutlined />, label: '平台 Token' },
    { key: 'analysis', icon: <SettingOutlined />, label: '分析参数' },
  ]

  return (
    <div style={{ padding: 24, display: 'flex', gap: 24, alignItems: 'flex-start' }}>
      <Card styles={{ body: { padding: 8 } }} style={{ width: 220, flexShrink: 0 }}>
        <Menu
          mode="vertical"
          selectedKeys={[section]}
          onClick={(e) => setSection(e.key as Section)}
          items={menuItems}
          style={{ border: 'none' }}
        />
      </Card>

      <Card loading={isLoading} style={{ flex: 1, maxWidth: 720 }}>
        {section === 'repo' && (
          <>
            <SectionHeader title="仓库接入" desc="代码仓库地址与默认分支配置" />
            <Field label="仓库地址">
              <CopyField value={settings.gitUrl ?? settings.repoUrl ?? '—'} />
            </Field>
            <Field label="默认分支">
              <Space>
                <Text code>{settings.defaultBranch ?? 'main'}</Text>
                <Tag color="blue">强制纳入分析</Tag>
              </Space>
            </Field>
            <Field label="Deploy Key">
              <Paragraph type="secondary" style={{ margin: 0 }}>
                只读部署密钥用于拉取私有仓库。请将公钥添加到代码托管平台的 Deploy
                Keys 设置中。
              </Paragraph>
            </Field>
          </>
        )}

        {section === 'webhook' && (
          <>
            <SectionHeader
              title="Webhook"
              desc="接收 push 事件以触发增量索引与分析"
            />
            <Field label="Webhook URL">
              <CopyField value={webhookUrl} />
            </Field>
            <Field label="Secret">
              <Input.Password
                placeholder="用于校验 webhook 签名"
                defaultValue={settings.webhookSecret}
              />
            </Field>
            <Field label="启用">
              <Switch defaultChecked={settings.webhookEnabled ?? true} />
            </Field>
          </>
        )}

        {section === 'apikey' && (
          <>
            <SectionHeader title="API Key" desc="用于程序化访问项目数据" />
            <div style={{ marginBottom: 16, textAlign: 'right' }}>
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => {
                  setCreatedKey(null)
                  setKeyModalOpen(true)
                }}
              >
                创建 Key
              </Button>
            </div>
            <Table
              rowKey="id"
              size="small"
              columns={keyColumns}
              dataSource={keys}
              pagination={false}
            />
            <Modal
              title="创建 API Key"
              open={keyModalOpen}
              onOk={createdKey ? () => setKeyModalOpen(false) : handleCreateKey}
              confirmLoading={createKey.isPending}
              onCancel={() => setKeyModalOpen(false)}
              okText={createdKey ? '完成' : '创建'}
              destroyOnClose
            >
              {createdKey ? (
                <div>
                  <Paragraph>
                    请妥善保存以下 Key,它只会显示一次:
                  </Paragraph>
                  <CopyField value={createdKey} />
                </div>
              ) : (
                <Form form={keyForm} layout="vertical">
                  <Form.Item
                    name="name"
                    label="名称"
                    rules={[{ required: true, message: '请输入名称' }]}
                  >
                    <Input placeholder="如 ci-pipeline" />
                  </Form.Item>
                </Form>
              )}
            </Modal>
          </>
        )}

        {section === 'platform' && (
          <>
            <SectionHeader
              title="平台 Token"
              desc="用于解析提交作者身份与拉取平台元数据"
            />
            <Field label="平台">
              <Tag color="blue">{settings.platform ?? 'GitHub'}</Tag>
            </Field>
            <Field label="Access Token">
              <Input.Password placeholder="平台访问令牌" />
            </Field>
            <Field label="解析覆盖率">
              <Text type="secondary">
                {settings.identityCoverage != null
                  ? `${settings.identityCoverage}% 提交已解析到平台身份`
                  : '尚未解析'}
              </Text>
            </Field>
          </>
        )}

        {section === 'analysis' && (
          <>
            <SectionHeader title="分析参数" desc="提交分析与模型路由配置" />
            <Field label="回溯口径">
              <Segmented
                options={['最近 30 天', '最近 100 次提交', '全部历史']}
                defaultValue={settings.backfillRange ?? '最近 100 次提交'}
              />
            </Field>
            <Field label="提交粒度">
              <Segmented
                options={['按提交', '按合并请求', '按天']}
                defaultValue={settings.commitGranularity ?? '按提交'}
              />
            </Field>
            <Field label="忽略提交信息">
              <Switch defaultChecked={settings.ignoreMessage ?? false} />
            </Field>
            <Field label="检测信息漂移">
              <Switch defaultChecked={settings.detectDrift ?? true} />
            </Field>
            <Field label="模型路由">
              <Space wrap>
                <Tag color="purple">分析: {settings.analyzeModel ?? 'gpt-4o-mini'}</Tag>
                <Tag color="cyan">嵌入: {settings.embedModel ?? 'text-embedding-3'}</Tag>
                <Tag color="geekblue">问答: {settings.qaModel ?? 'gpt-4o'}</Tag>
              </Space>
            </Field>
          </>
        )}
      </Card>
    </div>
  )
}
