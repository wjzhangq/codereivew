import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Input, Button, Checkbox, message } from 'antd'
import { UserOutlined, LockOutlined, ScanOutlined, InfoCircleOutlined } from '@ant-design/icons'
import { useAuthStore } from '../store/auth'

const CHIPS = ['Tree-sitter 图谱', 'sqlite-vec 检索', 'gitleaks · Semgrep', 'DuckDB 看板']

export default function Login() {
  const nav = useNavigate()
  const setToken = useAuthStore((s) => s.setToken)
  const [u, setU] = useState('admin')
  const [p, setP] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: u, password: p }),
      })
      if (!res.ok) throw new Error('登录失败')
      const data = await res.json()
      setToken(data.access_token ?? data.token, data.user)
      nav('/dashboard')
    } catch (e: any) {
      message.error(e?.message || '用户名或密码错误')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ height: '100vh', display: 'flex' }}>
      {/* 左侧品牌区 */}
      <div
        style={{
          flex: 1,
          background: 'linear-gradient(150deg, #312e81 0%, #4f46e5 55%, #6d28d9 100%)',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          padding: 56,
          color: '#fff',
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            position: 'absolute',
            inset: 0,
            opacity: 0.12,
            backgroundImage:
              'radial-gradient(circle at 20% 30%, #fff 0, transparent 38%), radial-gradient(circle at 80% 70%, #fff 0, transparent 32%)',
          }}
        />
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, position: 'relative' }}>
          <div
            style={{
              width: 38,
              height: 38,
              borderRadius: 9,
              background: 'rgba(255,255,255,.16)',
              display: 'grid',
              placeItems: 'center',
            }}
          >
            <ScanOutlined style={{ fontSize: 22 }} />
          </div>
          <span style={{ fontSize: 19, fontWeight: 650 }}>CodeReview</span>
        </div>
        <div style={{ position: 'relative' }}>
          <div
            style={{
              fontSize: 38,
              fontWeight: 700,
              lineHeight: 1.2,
              letterSpacing: '-.5px',
              marginBottom: 18,
            }}
          >
            看懂每一次改动,
            <br />
            守住每一处隐患。
          </div>
          <div style={{ fontSize: 16, opacity: 0.8, lineHeight: 1.7, maxWidth: 420 }}>
            自动化代码 Review 平台 — 结构图谱、逐 commit 理解、安全扫描、贡献汇总、代码问答与项目
            Wiki,一处接入,持续洞察。
          </div>
          <div style={{ display: 'flex', gap: 10, marginTop: 28, flexWrap: 'wrap' }}>
            {CHIPS.map((t) => (
              <span
                key={t}
                style={{
                  fontSize: 13,
                  padding: '5px 12px',
                  borderRadius: 20,
                  background: 'rgba(255,255,255,.14)',
                  border: '1px solid rgba(255,255,255,.18)',
                }}
              >
                {t}
              </span>
            ))}
          </div>
        </div>
        <div style={{ position: 'relative', fontSize: 13, opacity: 0.6 }}>
          本地账号体系 · 平台 token 仅用于身份解析,不用于登录
        </div>
      </div>

      {/* 右侧表单区 */}
      <div
        style={{
          width: 460,
          flexShrink: 0,
          display: 'grid',
          placeItems: 'center',
          background: '#fff',
          padding: 40,
        }}
      >
        <div style={{ width: '100%', maxWidth: 320 }}>
          <h1 style={{ fontSize: 24, fontWeight: 680, margin: '0 0 6px' }}>登录</h1>
          <p style={{ color: 'rgba(0,0,0,.45)', margin: '0 0 28px' }}>使用管理员分配的账号登录</p>

          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', marginBottom: 6, fontSize: 13, color: 'rgba(0,0,0,.65)' }}>
              用户名
            </label>
            <Input
              size="large"
              prefix={<UserOutlined />}
              value={u}
              onChange={(e) => setU(e.target.value)}
              placeholder="username"
              onPressEnter={submit}
            />
          </div>
          <div style={{ marginBottom: 10 }}>
            <label style={{ display: 'block', marginBottom: 6, fontSize: 13, color: 'rgba(0,0,0,.65)' }}>
              密码
            </label>
            <Input.Password
              size="large"
              prefix={<LockOutlined />}
              value={p}
              onChange={(e) => setP(e.target.value)}
              placeholder="password"
              onPressEnter={submit}
            />
          </div>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: 22,
            }}
          >
            <Checkbox defaultChecked>记住登录态</Checkbox>
            <a style={{ fontSize: 13 }}>忘记密码?</a>
          </div>
          <Button type="primary" size="large" block loading={loading} onClick={submit}>
            {loading ? '登录中…' : '登录'}
          </Button>
          <div
            style={{
              marginTop: 20,
              padding: 12,
              background: '#f7f8fa',
              borderRadius: 8,
              fontSize: 12.5,
              color: 'rgba(0,0,0,.45)',
              lineHeight: 1.6,
            }}
          >
            <InfoCircleOutlined style={{ marginRight: 4 }} />
            使用管理员分配的账号登录。接口/机器调用请使用 API Key。
          </div>
        </div>
      </div>
    </div>
  )
}
