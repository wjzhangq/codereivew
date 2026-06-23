/* hooks/api.ts — React Query hooks(按 dev.md 附录 A 契约) */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getList, getOne, post, put, patch, del } from '../api/client'

export const useProjects = () => useQuery({ queryKey: ['projects'], queryFn: () => getList<any>('/api/projects') })
export const useProject = (id: string) => useQuery({ queryKey: ['project', id], queryFn: () => getOne<any>(`/api/projects/${id}`), enabled: !!id })
export const useCreateProject = () => {
  const qc = useQueryClient()
  return useMutation({ mutationFn: (b: any) => post('/api/projects', b), onSuccess: () => qc.invalidateQueries({ queryKey: ['projects'] }) })
}
export const useReindex = (id: string) => useMutation({ mutationFn: () => post(`/api/projects/${id}/reindex`) })

export const useBranches = (id: string) => useQuery({ queryKey: ['branches', id], queryFn: () => getList<any>(`/api/projects/${id}/branches`), enabled: !!id })
export const useSyncRemote = (id: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => post(`/api/projects/${id}/sync`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['branches', id] }),
  })
}

export const useSetWhitelist = (id: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ name, whitelisted }: any) => put(`/api/projects/${id}/branches/${encodeURIComponent(name)}/whitelist`, { whitelisted }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['branches', id] }),
  })
}
export const useGraph = (id: string, branch?: string) => useQuery({ queryKey: ['graph', id, branch], queryFn: () => getOne<any>(`/api/projects/${id}/graph`, { branch }), enabled: !!id })

export const useCommits = (id: string, range = '30d') => useQuery({ queryKey: ['commits', id, range], queryFn: () => getList<any>(`/api/projects/${id}/commits`, { range }), enabled: !!id })
export const useAnalyzeCommits = (id: string) => useMutation({ mutationFn: () => post(`/api/projects/${id}/analyze`) })
export const useContributors = (id: string, mode: 'log' | 'blame') => useQuery({ queryKey: ['contrib', id, mode], queryFn: () => getOne<any>(`/api/projects/${id}/contributors`, { mode }), enabled: !!id })
export const useWeeklyReport = (id: string, params: { week?: string; llm?: boolean }) => useQuery({
  queryKey: ['weekly', id, params.week ?? 'last', params.llm ?? true],
  queryFn: () => getOne<any>(`/api/projects/${id}/weekly`, { week: params.week, llm: params.llm }),
  enabled: !!id,
})

export const useFindings = (id: string, status?: string) => useQuery({ queryKey: ['findings', id, status], queryFn: () => getList<any>(`/api/projects/${id}/findings`, { status }), enabled: !!id })
export const useScan = (id: string) => useMutation({ mutationFn: () => post(`/api/projects/${id}/scan`) })
export const useUpdateFinding = (id: string) => {
  const qc = useQueryClient()
  return useMutation({ mutationFn: ({ fid, status }: any) => patch(`/api/projects/${id}/findings/${fid}`, { status }), onSuccess: () => qc.invalidateQueries({ queryKey: ['findings', id] }) })
}

export const useAsk = (id: string) => useMutation({ mutationFn: (question: string) => post<any>(`/api/projects/${id}/qa`, { question }) })

export const useQASuggestions = (id: string) => useQuery({
  queryKey: ['qaSuggestions', id],
  queryFn: () => getOne<{ questions: string[] }>(`/api/projects/${id}/qa/suggestions`),
  enabled: !!id,
  staleTime: 10 * 60 * 1000,
})

export const useWikiList = (id: string) => useQuery({ queryKey: ['wikiList', id], queryFn: () => getList<any>(`/api/projects/${id}/wiki`), enabled: !!id })
export const useWikiPage = (id: string, page: string) => useQuery({ queryKey: ['wiki', id, page], queryFn: () => getOne<any>(`/api/projects/${id}/wiki/${page}`), enabled: !!id && !!page })
export const useRefreshWiki = (id: string) => useMutation({ mutationFn: () => post(`/api/projects/${id}/wiki/refresh`) })

export const useJobs = (status?: string) => useQuery({ queryKey: ['jobs', status], queryFn: () => getList<any>('/api/jobs', { status }), refetchInterval: 4000 })
export const useJobsFull = (status?: string) => useQuery({ queryKey: ['jobsFull', status], queryFn: () => getOne<any>('/api/jobs', { status }), refetchInterval: 4000 })
export const useJobDetail = (jobId?: string) => useQuery({ queryKey: ['job', jobId], queryFn: () => getOne<any>(`/api/jobs/${(jobId ?? '').replace('J-', '')}`), enabled: !!jobId })

// 给空面板用:取某项目某类任务的最新一条,据此区分 无任务/运行中/失败
export const useLatestJob = (project: string, types: string[]) => useQuery({
  queryKey: ['latestJob', project, types.join(',')],
  queryFn: async () => {
    const jobs = await getList<any>('/api/jobs')
    const mine = jobs.filter((j) => j.project === project && types.includes(j.type))
    return mine[0] ?? null  // 后端已按 created_at DESC 排序
  },
  enabled: !!project,
  refetchInterval: 4000,
})
export const useRetryJob = () => {
  const qc = useQueryClient()
  return useMutation({ mutationFn: (id: string) => post(`/api/jobs/${id.replace('J-', '')}/retry`), onSuccess: () => { qc.invalidateQueries({ queryKey: ['jobs'] }); qc.invalidateQueries({ queryKey: ['jobsFull'] }) } })
}

export const useUsers = () => useQuery({ queryKey: ['users'], queryFn: () => getList<any>('/api/users') })
export const useCreateUser = () => {
  const qc = useQueryClient()
  return useMutation({ mutationFn: (b: any) => post('/api/users', b), onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }) })
}
export const useUpdateUser = () => {
  const qc = useQueryClient()
  return useMutation({ mutationFn: ({ uid, ...b }: any) => patch(`/api/users/${uid}`, b), onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }) })
}
export const useIdentities = (id: string) => useQuery({ queryKey: ['identities', id], queryFn: () => getList<any>(`/api/projects/${id}/identities`), enabled: !!id })
export const useResolveIdentities = (id: string) => {
  const qc = useQueryClient()
  return useMutation({ mutationFn: () => post(`/api/projects/${id}/identities/resolve`), onSuccess: () => qc.invalidateQueries({ queryKey: ['identities', id] }) })
}

export const useProjectSettings = (id: string) => useQuery({ queryKey: ['settings', id], queryFn: () => getOne<any>(`/api/projects/${id}/settings`), enabled: !!id })
export const useCreateKey = (id: string) => {
  const qc = useQueryClient()
  return useMutation({ mutationFn: (b: any) => post(`/api/projects/${id}/keys`, b), onSuccess: () => qc.invalidateQueries({ queryKey: ['settings', id] }) })
}
export const useRevokeKey = (id: string) => {
  const qc = useQueryClient()
  return useMutation({ mutationFn: (kid: string) => del(`/api/projects/${id}/keys/${kid}`), onSuccess: () => qc.invalidateQueries({ queryKey: ['settings', id] }) })
}
