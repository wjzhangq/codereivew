import type { Config } from 'tailwindcss'

// Tailwind 仅做布局/间距工具类;视觉以 AntD token 为准。
// 颜色取 design_handoff README 的 Design Tokens 表。
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  corePlugins: { preflight: false }, // 不覆盖 AntD reset
  theme: {
    extend: {
      colors: {
        primary: '#4f46e5',
        'primary-hover': '#6366f1',
        'primary-bg': '#eef2ff',
        success: '#16a34a',
        warning: '#d97706',
        error: '#dc2626',
        info: '#2563eb',
        'sev-critical': '#dc2626',
        'sev-high': '#ea580c',
        'sev-medium': '#d97706',
        'sev-low': '#0891b2',
        'bg-layout': '#f5f6f8',
      },
      borderRadius: { card: '12px' },
    },
  },
  plugins: [],
} satisfies Config
