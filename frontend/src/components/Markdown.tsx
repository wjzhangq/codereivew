import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'

// react-markdown v10 移除了 code 的 inline 参数。
// 约定:块级代码由 <pre> 包裹,故在 pre 上套 .code-block,
// 行内 code(无 pre 父级)用 .code-inline。
const components: Components = {
  pre: ({ children }) => <pre className="code-block">{children}</pre>,
  code: ({ children, className, ...props }) => {
    // 块级代码的 code 元素带 language-* className 或被 pre 包裹;
    // 行内代码无 className。
    const isBlock = /language-/.test(className || '')
    return isBlock ? (
      <code className={className} {...props}>
        {children}
      </code>
    ) : (
      <code className="code-inline" {...props}>
        {children}
      </code>
    )
  },
}

export function Markdown({ children }: { children?: string | null }) {
  return (
    <div className="markdown-body">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {children || ''}
      </ReactMarkdown>
    </div>
  )
}
