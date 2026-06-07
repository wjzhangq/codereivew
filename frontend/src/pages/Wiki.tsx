import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { App, Button, Card, Empty, Space, Spin, Tag } from 'antd'
import { ReloadOutlined, MessageOutlined } from '@ant-design/icons'
import { useWikiList, useWikiPage, useRefreshWiki } from '../hooks/api'

type WikiPageItem = {
  slug: string
  title: string
  group?: string
  hasNewCommits?: boolean
  has_new_commits?: boolean
  fresh?: boolean
}

type Section = { heading?: string; title?: string; body?: string; content?: string; color?: string }

const SECTION_COLORS = ['#4f46e5', '#0891b2', '#7c3aed', '#d97706', '#16a34a']

export default function Wiki() {
  const { id = '' } = useParams()
  const { message } = App.useApp()
  const { data: pages = [], isLoading: listLoading } = useWikiList(id)
  const refresh = useRefreshWiki(id)
  const [activeSlug, setActiveSlug] = useState<string>('')

  const list = pages as WikiPageItem[]

  useEffect(() => {
    if (!activeSlug && list.length > 0) setActiveSlug(list[0].slug)
  }, [list, activeSlug])

  const { data: page, isLoading: pageLoading } = useWikiPage(id, activeSlug)

  const grouped = useMemo(() => {
    const g: Record<string, WikiPageItem[]> = {}
    for (const p of list) {
      const key = p.group || '未分组'
      ;(g[key] = g[key] || []).push(p)
    }
    return g
  }, [list])

  const isFresh = (p: WikiPageItem) => p.hasNewCommits ?? p.has_new_commits ?? p.fresh ?? false

  const doRefresh = async () => {
    try {
      await refresh.mutateAsync()
      message.success('已触发增量刷新,稍后查看更新')
    } catch {
      message.error('刷新失败')
    }
  }

  const sections: Section[] = page?.sections ?? []
  const modules: string[] = page?.modules ?? []

  return (
    <div className="fade-up" style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
      {/* 目录 */}
      <Card
        style={{ width: 260, flexShrink: 0, position: 'sticky', top: 0 }}
        styles={{ body: { padding: 12 } }}
      >
        <Button
          block
          type="primary"
          icon={<ReloadOutlined />}
          loading={refresh.isPending}
          onClick={doRefresh}
          style={{ marginBottom: 12 }}
        >
          增量刷新 Wiki
        </Button>

        {listLoading ? (
          <div style={{ textAlign: 'center', padding: 20 }}>
            <Spin size="small" />
          </div>
        ) : (
          Object.entries(grouped).map(([group, items]) => (
            <div key={group} style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, color: 'var(--text-3)', padding: '4px 8px' }}>{group}</div>
              {items.map((p) => (
                <div
                  key={p.slug}
                  onClick={() => setActiveSlug(p.slug)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    padding: '8px 10px',
                    borderRadius: 6,
                    cursor: 'pointer',
                    fontSize: 13,
                    background: activeSlug === p.slug ? 'var(--primary-bg)' : 'transparent',
                    color: activeSlug === p.slug ? 'var(--primary)' : 'var(--text)',
                    fontWeight: activeSlug === p.slug ? 600 : 400,
                  }}
                >
                  <span style={{ flex: 1 }}>{p.title}</span>
                  {isFresh(p) && <span className="pulse-dot fresh" />}
                </div>
              ))}
            </div>
          ))
        )}
      </Card>

      {/* 文档 */}
      <Card style={{ flex: 1 }} styles={{ body: { padding: '32px 40px', maxWidth: 820, margin: '0 auto' } }}>
        {pageLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Spin />
          </div>
        ) : !page ? (
          <Empty description="选择左侧页面查看 Wiki" />
        ) : (
          <div>
            <Space style={{ marginBottom: 12 }}>
              <Tag color="purple">LLM 由社区结构 + commit 理解生成</Tag>
              {page.updatedAt || page.updated_at ? (
                <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
                  更新于 {page.updatedAt || page.updated_at}
                </span>
              ) : null}
            </Space>

            <h1 style={{ fontSize: 28, fontWeight: 700, marginTop: 8, marginBottom: 12 }}>{page.title}</h1>

            {modules.length > 0 && (
              <Space size={6} wrap style={{ marginBottom: 24 }}>
                <span style={{ fontSize: 12, color: 'var(--text-3)' }}>涉及模块:</span>
                {modules.map((m) => (
                  <Tag key={m} style={{ marginInlineEnd: 0 }}>{m}</Tag>
                ))}
              </Space>
            )}

            {sections.length === 0 ? (
              <div style={{ color: 'var(--text-2)', lineHeight: 1.8 }}>{page.content || page.body || '暂无内容'}</div>
            ) : (
              sections.map((s, i) => (
                <div key={i} style={{ marginBottom: 28 }}>
                  <h2 style={{
                    fontSize: 18,
                    fontWeight: 650,
                    borderLeft: `3px solid ${s.color || SECTION_COLORS[i % SECTION_COLORS.length]}`,
                    paddingLeft: 12,
                    marginBottom: 12,
                  }}>
                    {s.heading || s.title}
                  </h2>
                  <div style={{ color: 'var(--text-2)', lineHeight: 1.8, whiteSpace: 'pre-wrap' }}>
                    {s.body || s.content}
                  </div>
                </div>
              ))
            )}

            <Card
              style={{ marginTop: 32, background: 'var(--primary-bg)', border: 'none' }}
              styles={{ body: { padding: 16, display: 'flex', alignItems: 'center', justifyContent: 'space-between' } }}
            >
              <span>有疑问?直接就该模块向代码问答提问。</span>
              <Button type="primary" icon={<MessageOutlined />} href={`/projects/${id}/qa`}>
                去问答
              </Button>
            </Card>
          </div>
        )}
      </Card>
    </div>
  )
}
