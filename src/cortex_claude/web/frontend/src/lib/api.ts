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
  return response<T>(res)
}

async function response<T>(res: Response): Promise<T> {
  const data = await res.json()
  if (!res.ok || data.ok === false) throw new Error(data.error || `${res.status} ${res.statusText}`)
  return data as T
}

async function send<T>(path: string, method: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  return response<T>(res)
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

export interface ProjectMemory {
  changed_files?: string[]
  review_queue?: { id: string; section: string; sources: string[]; reason: string }[]
  analysis?: {
    files: { path: string; status: string; symbols: { name: string; kind: string; line: number; calls: string[]; imports: string[] }[] }[]
    flows: { caller: string; callee: string; path: string; line: number; resolution: string }[]
    coverage: { discovered: number; analyzed: number; partial: boolean; unavailable: string[]; parser_unavailable: number }
    scan: { read_files: number; reused_files: number; read_bytes: number; changed: string[]; removed: string[] }
  }
  name: string; origin: string; purpose: string; revision: number; updated_at: number; needs_review: boolean; truncated: boolean
  modules: { name: string; path: string; manifest: string; purpose: string; stack: string[]; entrypoints: string[]; commands: { name: string; command: string; definition: string; cwd: string }[] }[]
  notes: { id: string; section: string; content: string; sources: string[]; needs_review: boolean }[]
  documents: { path: string; headings: { title: string; line: number }[] }[]
  structure: string[]; warnings: string[]
}
export const fetchProjects = () => get<{ items: ProjectMemory[] }>('/api/projects')
export const refreshProject = (origin: string) => send<ProjectMemory | { status: 'disabled' }>('/api/projects/refresh', 'POST', { origin })
export interface ExecutionEntry { id: string; content: string; created_at: number; _scope: string }
export const fetchExecutions = (q: string, offset = 0) => get<Page<ExecutionEntry>>(`/api/executions${qs({ q, offset, limit: 30 })}`)

export interface Lesson {
  has_conflict: boolean
  feedback: Record<string, number>
  id: string
  topic: string
  content: string
  state: 'candidate' | 'active' | 'superseded' | 'stale'
  applicability: 'personal' | 'transferable' | 'context'
  origin: string
  explicit: number
  confirmations: number
  contexts: number
  kind: 'preference' | 'experience'
  conditions: string
  validation: 'not-required' | 'pending' | 'passed' | 'failed'
  stale_reason: string
  expires_at: number | null
}

export interface LessonDetail {
  details: Record<string, string>
  conditions: Record<string, string[]>
  dependencies: Record<string, string>
  evidence: { origin: string; source: string; observed_at: number }[]
  outcomes: { outcome: string; origin: string; command: string | null; observed_at: number }[]
}

interface TaskVariant {
  runs: number
  quality: number
  tokens: number
  elapsed_ms: number
  tool_calls: number
  failures: number
}

export interface LearningData {
  lessons: Lesson[]
  stats: {
    conflicts_open: number
    tasks_open: number
    selection: Record<string, number>
    feedback: Record<string, number>
    reads: { full: number; delta: number; unchanged: number; emitted_tokens: number; avoided_tokens: number }
    states: Record<string, number>
    confirmations_required: number
    injected_tokens: number
    repeat_tokens_avoided: number
    max_context_tokens: number
    max_session_tokens: number
    detail_tokens: number
    semantic_status: string
    semantic_indexed: number
    usage: { sessions: number; messages: number; input_tokens: number; output_tokens: number; cache_read_tokens: number; cache_creation_tokens: number }
    comparisons: { task: string; model: string; baseline: TaskVariant; memory: TaskVariant; token_change_percent: number | null; quality_preserved: boolean }[]
  }
}

export const fetchLearning = () => get<LearningData>('/api/learning')
export const fetchLesson = (id: string) => get<LessonDetail>(`/api/learning/${encodeURIComponent(id)}`)
export const forgetLesson = (id: string) =>
  send<{ ok: boolean }>(`/api/learning/${encodeURIComponent(id)}`, 'DELETE')

let feedbackIdentity: string
try {
  feedbackIdentity = localStorage.getItem('cortex-feedback') || `dashboard:${crypto.randomUUID()}`
  localStorage.setItem('cortex-feedback', feedbackIdentity)
} catch { feedbackIdentity = `dashboard:${crypto.randomUUID()}` }
export const assessLesson = (id: string, assessment: 'useful' | 'irrelevant' | 'corrected') =>
  send(`/api/learning/${encodeURIComponent(id)}/feedback`, 'POST', { assessment, session_id: feedbackIdentity })

export interface Conflict {
  id: string; topic: string; reason: string; created_at: number
  left_id: string; right_id: string; left_content: string; right_content: string
  left_conditions: string; right_conditions: string
  left_evidence: LessonDetail['evidence']; right_evidence: LessonDetail['evidence']
}
export const fetchConflicts = () => get<{ items: Conflict[] }>('/api/conflicts')
export const resolveConflict = (id: string, choice: string, conditions?: Record<string, string[]>) =>
  send(`/api/conflicts/${encodeURIComponent(id)}/resolve`, 'POST', { choice, conditions })

export interface WorkItem {
  source: 'automatic' | 'assistant'; client: string
  id: string; origin: string; title: string; summary: string; next_step: string
  decisions: string[]; pending: string[]; dependencies: Record<string, string>
  revision: number; state: 'open' | 'complete'; needs_review: boolean; updated_at: number
}

export interface BackupSnapshot { id: string; created_at: number; verified_at: number; size: number; files: number }
export interface MemoryProbe { status?: 'passed' | 'failed' | 'unreadable'; completed_at?: number; elapsed_ms?: number; checks?: { name: string; passed: boolean; error?: string }[]; client_activation_tested?: boolean }
export interface DiagnosticHistory { checked_at?: number; codes?: string[]; events?: { at: number; status: string; codes: string[] }[] }
export interface RecoveryHealth {
  self_test: MemoryProbe; diagnostics: DiagnosticHistory
  version: string; status: 'healthy' | 'attention'; issues: string[]
  daemon: { running: boolean; semantic: string }
  last_saved_at: number; last_processed_at: number | null; last_restore_test_at: number | null
  queue: { pending: number; failures: number; oldest_at: number | null; items: { id: string; kind: string; attempts: number; error: string | null; created_at: number; next_attempt: number }[] }
  backups: BackupSnapshot[]
  policy: { auto_backup: boolean; interval_hours: number; keep: number; mirror_configured: boolean; auto_checkpoints: boolean }
  disk_free_bytes: number; databases: { name: string; readable: boolean }[]
  clients: Record<string, { configured: boolean; last_hook_at: number | null; last_mcp_at: number | null; last_received_at?: number | null; last_saved_at?: number | null; last_context_at?: number | null }>
  services: Record<string, { installed: boolean; label: string }>
}
export const fetchHealth = () => get<RecoveryHealth>('/api/health')
export const runMemoryProbe = () => send<MemoryProbe>('/api/recovery/self-test', 'POST', {})
export const runDiagnostics = () => send<DiagnosticHistory>('/api/recovery/diagnose', 'POST', {})
export const createBackup = () => send<{ id: string; verified: boolean }>('/api/recovery/backup', 'POST', {})
export const verifyBackup = (id: string) => send<{ verified: boolean }>('/api/recovery/verify', 'POST', { id })
export const restoreBackup = (id: string) => send<{ destination: string }>('/api/recovery/restore', 'POST', { id })
export const retryPending = () => send<{ scheduled: number }>('/api/recovery/retry', 'POST', {})
export const fetchTasks = () => get<{ items: WorkItem[] }>('/api/tasks')
export const changeTask = (item: WorkItem, action: 'complete' | 'forget') =>
  send(`/api/tasks/${encodeURIComponent(item.id)}`, 'POST', { action, expected_revision: item.revision })

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
