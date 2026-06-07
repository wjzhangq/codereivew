/**
 * theme.ts — AntD v5 主题 token
 * 把 design_handoff README "Design Tokens" 一节逐项映射为 ConfigProvider theme。
 * 严重等级色/图谱色等 AntD 未覆盖的用 CSS 变量(global.css)。
 */
import type { ThemeConfig } from 'antd'

export const theme: ThemeConfig = {
  token: {
    colorPrimary: '#4f46e5',
    colorSuccess: '#16a34a',
    colorWarning: '#d97706',
    colorError: '#dc2626',
    colorInfo: '#2563eb',
    borderRadius: 8,
    borderRadiusSM: 6,
    borderRadiusLG: 12,
    colorBgLayout: '#f5f6f8',
    colorBgContainer: '#ffffff',
    colorBorder: '#e5e7eb',
    colorBorderSecondary: '#f0f0f0',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Helvetica Neue", Helvetica, Arial, sans-serif',
    fontFamilyCode: '"SF Mono", "JetBrains Mono", "Roboto Mono", Menlo, Consolas, monospace',
    fontSize: 14,
    lineHeight: 1.5715,
    controlHeight: 36,
    boxShadow: '0 1px 2px rgba(0,0,0,.04), 0 1px 6px -1px rgba(0,0,0,.02)',
    boxShadowSecondary: '0 4px 12px rgba(0,0,0,.06), 0 1px 3px rgba(0,0,0,.04)',
    boxShadowTertiary: '0 6px 20px rgba(0,0,0,.10), 0 2px 6px rgba(0,0,0,.05)',
  },
  components: {
    Layout: { siderBg: '#ffffff', headerBg: '#ffffff' },
    Menu: { itemHeight: 40, itemBorderRadius: 6, itemSelectedBg: '#eef2ff', itemSelectedColor: '#4f46e5' },
    Table: { headerBg: '#fafbfc', rowHoverBg: '#f5f6f8' },
    Card: { borderRadiusLG: 12, paddingLG: 20 },
    Drawer: { paddingLG: 24 },
    Tag: { borderRadiusSM: 6 },
  },
}
