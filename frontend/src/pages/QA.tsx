import { useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Button, Card, Input, Space, Spin, Tag } from 'antd'
import { SendOutlined, StarOutlined } from '@ant-design/icons'
import { useAsk, useQASuggestions } from '../hooks/api'
import { Avatar } from '../components/widgets'

// 接口不可用时的本地兜底建议
const FALLBACK_SUGGESTIONS = [
  '项目整体架构是怎样的?有哪些核心模块?',
  '最近的改动主要集中在哪些模块?',
  '项目里有哪些关键的设计决策和取舍?',
  '核心功能的实现思路是怎样的?',
]

type EvidenceItem = { type: string; count: number }
type HistoryItem = { sha: string; author?: string; summary: string; problem?: string; approach?: string }
type Message = {
  role: 'user' | 'ai'
  content: string
  evidence?: EvidenceItem[]
  history?: HistoryItem[]
  modules?: string[]
}

const EVIDENCE_COLOR: Record<string, string> = {
  graph: '#4f46e5',
  vector: '#7c3aed',
  history: '#0891b2',
}

const EVIDENCE_LABEL: Record<string, string> = {
  graph: '图谱',
  vector: '向量',
  history: '演进史',
}

export default function QA() {
  const { id = '' } = useParams()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const ask = useAsk(id)
  const { data: suggData, isLoading: suggLoading } = useQASuggestions(id)
  const suggestions = suggData?.questions?.length ? suggData.questions : FALLBACK_SUGGESTIONS

  const submit = async (q?: string) => {
    const question = (q || input).trim()
    if (!question) return
    setInput('')
    const userMsg: Message = { role: 'user', content: question }
    setMessages((prev) => [...prev, userMsg])
    try {
      const res = await ask.mutateAsync(question)
      const aiMsg: Message = {
        role: 'ai',
        content: res.answer || '',
        evidence: res.evidence,
        history: res.history,
        modules: res.modules,
      }
      setMessages((prev) => [...prev, aiMsg])
    } catch {
      setMessages((prev) => [...prev, { role: 'ai', content: '抱歉,检索或生成失败。请稍后重试。' }])
    }
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 100)
  }

  const renderAnswer = (text: string) => {
    // Simple bold support: **text**
    const parts = text.split(/(\*\*[^*]+\*\*)/g)
    return parts.map((p, i) =>
      p.startsWith('**') && p.endsWith('**') ? (
        <strong key={i}>{p.slice(2, -2)}</strong>
      ) : (
        <span key={i}>{p}</span>
      ),
    )
  }

  const isEmpty = messages.length === 0

  return (
    <div className="fade-up">
      <Card
        title={
          <Space>
            <span>代码问答</span>
            <span style={{ fontSize: 12, color: 'var(--text-3)', fontWeight: 400 }}>
              检索来源:图谱 + 向量 + 演进史
            </span>
          </Space>
        }
        style={{ minHeight: 'calc(100vh - 250px)' }}
        styles={{ body: { display: 'flex', flexDirection: 'column', minHeight: 480, padding: 0 } }}
      >
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 20px 0' }}>
          {isEmpty ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', paddingBottom: 60, textAlign: 'center' }}>
              <div style={{
                width: 56, height: 56, borderRadius: 14,
                background: 'linear-gradient(135deg, #4f46e5, #7c3aed)',
                display: 'grid', placeItems: 'center', marginBottom: 16,
              }}>
                <StarOutlined style={{ fontSize: 28, color: '#fff' }} />
              </div>
              <h3 style={{ marginBottom: 6 }}>基于图谱 + 向量 + 演进史的智能问答</h3>
              <p style={{ color: 'var(--text-3)', maxWidth: 480, lineHeight: 1.7 }}>
                提问关于项目实现的任何问题。系统结合代码结构图谱、语义向量检索和提交演进历史,
                给出当前实现细节与历史上出现过的不同思路。
              </p>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginTop: 18, maxWidth: 500 }}>
                {suggLoading ? (
                  <div style={{ gridColumn: '1 / -1', textAlign: 'center', padding: 20 }}>
                    <Spin size="small" />
                    <span style={{ marginLeft: 8, color: 'var(--text-3)', fontSize: 13 }}>正在生成项目相关问题…</span>
                  </div>
                ) : (
                  suggestions.map((s) => (
                    <div
                      key={s}
                      onClick={() => submit(s)}
                      style={{
                        cursor: 'pointer',
                        padding: '10px 14px',
                        borderRadius: 10,
                        border: '1px solid var(--border)',
                        fontSize: 13,
                        lineHeight: 1.5,
                        transition: 'all .15s',
                      }}
                      onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--primary)' }}
                      onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--border)' }}
                    >
                      {s}
                    </div>
                  ))
                )}
              </div>
            </div>
          ) : (
            messages.map((msg, i) => (
              <div
                key={i}
                style={{
                  display: 'flex',
                  justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                  marginBottom: 18,
                }}
              >
                {msg.role === 'ai' && (
                  <div style={{
                    width: 32, height: 32, borderRadius: 8, marginRight: 10, flexShrink: 0,
                    background: 'linear-gradient(135deg, #4f46e5, #7c3aed)',
                    display: 'grid', placeItems: 'center',
                  }}>
                    <StarOutlined style={{ color: '#fff', fontSize: 16 }} />
                  </div>
                )}
                <div style={{
                  maxWidth: '70%',
                  padding: '10px 14px',
                  borderRadius: msg.role === 'user' ? '14px 14px 4px 14px' : '14px 14px 14px 4px',
                  background: msg.role === 'user' ? 'var(--primary)' : 'var(--fill-quaternary, #f7f8fa)',
                  color: msg.role === 'user' ? '#fff' : 'var(--text)',
                  lineHeight: 1.7,
                  fontSize: 14,
                }}>
                  {msg.role === 'ai' && msg.evidence && msg.evidence.length > 0 && (
                    <div style={{ marginBottom: 10, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      {msg.evidence.map((e) => (
                        <Tag key={e.type} color={EVIDENCE_COLOR[e.type]} style={{ marginInlineEnd: 0 }}>
                          {EVIDENCE_LABEL[e.type] || e.type} ×{e.count}
                        </Tag>
                      ))}
                    </div>
                  )}

                  <div>{renderAnswer(msg.content)}</div>

                  {msg.role === 'ai' && msg.history && msg.history.length > 0 && (
                    <div style={{ marginTop: 12, paddingTop: 10, borderTop: '1px solid var(--border-2)' }}>
                      <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 8 }}>历史上出现过的思路</div>
                      {msg.history.map((h) => (
                        <div key={h.sha} style={{ padding: '6px 10px', background: '#fff', borderRadius: 8, marginBottom: 6, border: '1px solid var(--border-2)' }}>
                          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                            <span className="code-inline">{h.sha?.slice(0, 7)}</span>
                            {h.author && <Avatar name={h.author} size={20} />}
                          </div>
                          <div style={{ fontSize: 13, marginTop: 4 }}>{h.summary}</div>
                        </div>
                      ))}
                    </div>
                  )}

                  {msg.role === 'ai' && msg.modules && msg.modules.length > 0 && (
                    <div style={{ marginTop: 10, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                      {msg.modules.map((m) => (
                        <Tag key={m} style={{ marginInlineEnd: 0 }}>{m}</Tag>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))
          )}
          {ask.isPending && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-3)', marginBottom: 16 }}>
              <Spin size="small" />
              检索图谱与向量,归纳演进史…
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div style={{ padding: '12px 20px', borderTop: '1px solid var(--border-2)', display: 'flex', gap: 10 }}>
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onPressEnter={() => submit()}
            placeholder="输入问题…"
            size="large"
            disabled={ask.isPending}
          />
          <Button
            type="primary"
            size="large"
            icon={<SendOutlined />}
            loading={ask.isPending}
            onClick={() => submit()}
          />
        </div>
      </Card>
    </div>
  )
}
