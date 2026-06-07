/* store/auth.ts — 登录态 + 当前用户 + 侧栏折叠(zustand,持久化 token) */
import { create } from 'zustand'

interface User {
  id: string
  username: string
  name: string
  role: 'admin' | 'user'
}

interface AuthState {
  token: string | null
  user: User | null
  collapsed: boolean
  setAuth: (token: string, user: User) => void
  logout: () => void
  toggleCollapsed: () => void
}

const stored = localStorage.getItem('cr_auth')
const init = stored ? JSON.parse(stored) : { token: null, user: null }

export const useAuthStore = create<AuthState>((set, get) => ({
  token: init.token,
  user: init.user,
  collapsed: false,
  setAuth: (token, user) => {
    localStorage.setItem('cr_auth', JSON.stringify({ token, user }))
    set({ token, user })
  },
  logout: () => {
    localStorage.removeItem('cr_auth')
    set({ token: null, user: null })
  },
  toggleCollapsed: () => set({ collapsed: !get().collapsed }),
}))
