export interface ScopeInfo {
  name: string
  memories: number
  facts: number
  clusters: number
  size: number
}

export interface TagInfo {
  name: string
  count: number
}

export interface Overview {
  totals: { memories: number; facts: number; clusters: number; size: number }
  scopes: ScopeInfo[]
  tags: TagInfo[]
  growth: { day: number; count: number }[]
}

export interface Cluster {
  id: number
  scope: string
  label: string | null
  member_count: number
  updated_at: number
}

export interface Memory {
  id: string
  content: string
  summary: string | null
  tags: string
  scope: string
  cluster_id: number | null
  size: number
  created_at: number
  accessed_at: number
  access_count: number
  decay_score: number
  _scope: string
}

export interface Fact {
  subject: string
  relation: string
  object: string
  confidence: number
}

export interface Graph {
  nodes: { id: string; label: string; weight: number }[]
  edges: { source: string; target: string; label: string; confidence: number }[]
  truncated: boolean
  total_nodes: number
  total_edges: number
}

export interface ClusterDetail {
  cluster: Cluster
  scope: string
  graph: Graph
  memories: Memory[]
}

export interface Page<T> {
  items: T[]
  total: number
}

export type CleanupRule =
  | { type: 'tag'; value: string }
  | { type: 'cluster'; value: number; scope?: string }
  | { type: 'scope'; value: string }
  | { type: 'pattern'; value: string }

export interface CleanupPreview {
  count: number
  size: number
  by_scope: { scope: string; count: number }[]
  sample: { id: string; content: string; tags: string; created_at: number; _scope: string }[]
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

async function send<T>(path: string, method: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

function qs(params: Record<string, string | number | undefined | null>): string {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') p.set(k, String(v))
  }
  const s = p.toString()
  return s ? `?${s}` : ''
}

export const fetchOverview = () => get<Overview>('/api/overview')

export const fetchClusters = (o: {
  scope?: string
  q?: string
  limit?: number
  offset?: number
  sort?: string
}) => get<Page<Cluster>>(`/api/clusters${qs(o)}`)

export const fetchCluster = (id: number, scope?: string) =>
  get<ClusterDetail>(`/api/clusters/${id}${qs({ scope })}`)

export const fetchMemories = (o: {
  scope?: string
  tag?: string
  cluster?: number
  q?: string
  sort?: string
  limit?: number
  offset?: number
}) => get<Page<Memory>>(`/api/memories${qs(o)}`)

export const fetchMemory = (id: string) =>
  get<{ memory: Memory; facts: Fact[] }>(`/api/memory/${encodeURIComponent(id)}`)

export const fetchEntity = (name: string) =>
  get<{ facts: Fact[]; memories: Memory[]; graph: Graph }>(`/api/entity${qs({ name })}`)

export const deleteMemory = (id: string) =>
  send<{ ok: boolean }>(`/api/memory/${encodeURIComponent(id)}`, 'DELETE')

export const updateMemory = (id: string, data: { content?: string; tags?: string[] }) =>
  send<{ ok: boolean }>(`/api/memory/${encodeURIComponent(id)}`, 'PUT', data)

export const previewCleanup = (rules: CleanupRule[]) =>
  send<CleanupPreview>('/api/cleanup/preview', 'POST', { rules })

export const executeCleanup = (rules: CleanupRule[]) =>
  send<{ ok: boolean; deleted: number }>('/api/cleanup/execute', 'POST', { rules })

// ── formatting ───────────────────────────────────────────────

export function formatCount(n: number): string {
  return n.toLocaleString('pt-BR')
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
}

export function formatDate(ts: number): string {
  if (!ts) return ''
  return new Date(ts).toLocaleDateString('pt-BR', {
    day: '2-digit',
    month: 'short',
    year: '2-digit',
  })
}

export function formatDateTime(ts: number): string {
  if (!ts) return ''
  return new Date(ts).toLocaleString('pt-BR', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function parseTags(raw: string): string[] {
  try {
    const v = JSON.parse(raw || '[]')
    return Array.isArray(v) ? v : []
  } catch {
    return []
  }
}
