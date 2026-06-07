/* api/client.ts — axios 实例 + 统一拆包 */
import axios from 'axios'
import { useAuthStore } from '../store/auth'

export const http = axios.create({ baseURL: '/' })

http.interceptors.request.use((cfg) => {
  const token = useAuthStore.getState().token
  if (token) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

http.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      useAuthStore.getState().logout()
      if (location.pathname !== '/login') location.href = '/login'
    }
    return Promise.reject(err)
  },
)

/** list 接口返回 {data:[...]},统一取 data 字段 */
export async function getList<T>(url: string, params?: any): Promise<T[]> {
  const r = await http.get(url, { params })
  return r.data.data ?? r.data
}

export async function getOne<T>(url: string, params?: any): Promise<T> {
  const r = await http.get(url, { params })
  return r.data
}

export async function post<T>(url: string, body?: any): Promise<T> {
  const r = await http.post(url, body)
  return r.data
}

export async function put<T>(url: string, body?: any): Promise<T> {
  const r = await http.put(url, body)
  return r.data
}

export async function patch<T>(url: string, body?: any): Promise<T> {
  const r = await http.patch(url, body)
  return r.data
}

export async function del<T>(url: string): Promise<T> {
  const r = await http.delete(url)
  return r.data
}
