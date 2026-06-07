/* layout/AppLayout.tsx — 三段式外壳:Sidebar + Header + 内容区 */
import { Layout, Menu, Input, Badge, Dropdown, Select } from 'antd'
import {
  AppstoreOutlined, ApartmentOutlined, SafetyOutlined, BarChartOutlined,
  MessageOutlined, BookOutlined, SettingOutlined, TeamOutlined, BellOutlined,
  SearchOutlined, MenuFoldOutlined, MenuUnfoldOutlined, ScanOutlined,
  DownOutlined, LogoutOutlined, DatabaseOutlined, UserOutlined,
} from '@ant-design/icons'
import { Outlet, useNavigate, useParams, useLocation } from 'react-router-dom'
import { useAuthStore } from '../store/auth'
import { useProjects, useJobs, useFindings } from '../hooks/api'

const { Sider, Header, Content } = Layout

const PROJECT_TABS = [
  { key: 'overview', label: '概览 · 图谱', icon: <ApartmentOutlined /> },
  { key: 'security', label: '安全面板', icon: <SafetyOutlined /> },
  { key: 'reports', label: '周期 / 贡献报告', icon: <BarChartOutlined /> },
  { key: 'qa', label: '代码问答', icon: <MessageOutlined /> },
  { key: 'wiki', label: '项目 Wiki', icon: <BookOutlined /> },
  { key: 'settings', label: '项目设置', icon: <SettingOutlined /> },
]

export default function AppLayout() {
  const nav = useNavigate()
  const loc = useLocation()
  const { id: projectId, tab } = useParams()
  const { collapsed, toggleCollapsed, user, logout } = useAuthStore()
  const { data: projects = [] } = useProjects()
  const { data: jobs = [] } = useJobs()
  const { data: findings = [] } = useFindings(projectId || '', 'new')

  const runningJobs = jobs.filter((j: any) => j.status === 'running').length
  const curProject = projects.find((p: any) => p.id === projectId) || projects[0]
  const inProject = loc.pathname.startsWith('/projects/')

  const globalItems = [
    { key: '/dashboard', icon: <AppstoreOutlined />, label: '工作台' },
    { key: '/jobs', icon: <ApartmentOutlined />, label: <Badge count={runningJobs} size="small" offset={[10, 0]}>任务中心</Badge> },
  ]
  const projectItems = curProject ? PROJECT_TABS.map((t) => ({
    key: `/projects/${curProject.id}/${t.key}`,
    icon: t.icon,
    label: t.key === 'security'
      ? <Badge count={findings.length} size="small" offset={[10, 0]}>{t.label}</Badge>
      : t.label,
  })) : []

  const selectedKey = inProject ? `/projects/${projectId}/${tab || 'overview'}` : loc.pathname
  const crumbTab = PROJECT_TABS.find((t) => t.key === tab)?.label

  return (
    <Layout style={{ height: '100vh' }}>
      <Sider width={224} collapsedWidth={64} collapsed={collapsed} theme="light" style={{ borderRight: '1px solid var(--border-2)' }}>
        <div onClick={() => nav('/dashboard')} style={{ height: 56, display: 'flex', alignItems: 'center', gap: 10, padding: '0 16px', cursor: 'pointer' }}>
          <div style={{ width: 28, height: 28, borderRadius: 8, background: 'linear-gradient(135deg,#4f46e5,#7c3aed)', display: 'grid', placeItems: 'center', color: '#fff' }}><ScanOutlined /></div>
          {!collapsed && <span style={{ fontWeight: 700, fontSize: 16 }}>CodeReview</span>}
        </div>
        {!collapsed && curProject && (
          <div style={{ padding: '4px 12px 8px' }}>
            <Select value={curProject.id} variant="filled" style={{ width: '100%' }} suffixIcon={<DownOutlined />}
              prefix={<DatabaseOutlined style={{ color: 'var(--primary)' }} />}
              options={projects.map((p: any) => ({ value: p.id, label: p.name }))}
              onChange={(v) => nav(`/projects/${v}/${inProject ? tab || 'overview' : 'overview'}`)} />
          </div>
        )}
        <Menu mode="inline" selectedKeys={[selectedKey]} items={globalItems} onClick={(e) => nav(e.key)} style={{ border: 'none' }} />
        {!collapsed && <div style={{ padding: '8px 16px 4px', fontSize: 12, color: 'var(--text-3)' }}>当前项目</div>}
        {curProject && <Menu mode="inline" selectedKeys={[selectedKey]} items={projectItems} onClick={(e) => nav(e.key)} style={{ border: 'none' }} />}
        {user?.role === 'admin' && <>
          {!collapsed && <div style={{ padding: '8px 16px 4px', fontSize: 12, color: 'var(--text-3)' }}>系统</div>}
          <Menu mode="inline" selectedKeys={[selectedKey]} items={[{ key: '/users', icon: <TeamOutlined />, label: '用户管理' }]} onClick={(e) => nav(e.key)} style={{ border: 'none' }} />
        </>}
      </Sider>
      <Layout>
        <Header style={{ height: 56, display: 'flex', alignItems: 'center', padding: '0 20px', borderBottom: '1px solid var(--border-2)', gap: 16 }}>
          <span style={{ cursor: 'pointer', color: 'var(--text-3)' }} onClick={toggleCollapsed}>{collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}</span>
          <div style={{ color: 'var(--text-2)', fontSize: 14 }}>
            <span style={{ cursor: 'pointer' }} onClick={() => nav('/dashboard')}>工作台</span>
            {inProject && curProject && <> › <span>{curProject.name}</span></>}
            {inProject && crumbTab && <> › <span style={{ color: 'var(--text)' }}>{crumbTab}</span></>}
          </div>
          <div style={{ flex: 1 }} />
          <Input prefix={<SearchOutlined />} placeholder="搜索代码 / 提交 / 模块…" style={{ width: 240 }}
            suffix={<span style={{ fontSize: 11, color: 'var(--text-4)', border: '1px solid var(--border)', borderRadius: 4, padding: '1px 5px' }}>⌘K</span>} />
          <Badge dot><BellOutlined style={{ fontSize: 18, color: 'var(--text-2)', cursor: 'pointer' }} onClick={() => nav('/jobs')} /></Badge>
          <Dropdown menu={{ items: [
            { key: 'users', icon: <UserOutlined />, label: '账号设置', onClick: () => nav('/users') },
            { type: 'divider' as const },
            { key: 'logout', icon: <LogoutOutlined />, danger: true, label: '退出登录', onClick: () => { logout(); nav('/login') } },
          ] }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
              <span style={{ width: 28, height: 28, borderRadius: '50%', background: 'var(--primary)', color: '#fff', display: 'grid', placeItems: 'center', fontSize: 12, fontWeight: 600 }}>{(user?.name || 'AD').slice(0, 2)}</span>
              <div style={{ lineHeight: 1.2 }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>{user?.name}</div>
                <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{user?.role}</div>
              </div>
              <DownOutlined style={{ fontSize: 12, color: 'var(--text-3)' }} />
            </div>
          </Dropdown>
        </Header>
        <Content style={{ overflowY: 'auto' }}>
          <div className="fade-up" style={{ padding: 24, maxWidth: 1480, margin: '0 auto' }}><Outlet /></div>
        </Content>
      </Layout>
    </Layout>
  )
}
