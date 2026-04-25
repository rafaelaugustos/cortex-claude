export interface Stats {
  total_memories: number
  total_facts: number
  total_size: number
  scopes: { name: string; memories: number; facts: number; size: number }[]
}

export interface Memory {
  id: string
  content: string
  summary: string | null
  tags: string
  scope: string
  created_at: number
  accessed_at: number
  access_count: number
  decay_score: number
  _scope: string
}

export interface GraphData {
  nodes: { id: string; label: string; weight: number }[]
  edges: { source: string; target: string; label: string; confidence: number }[]
}

export interface EntityData {
  facts: { subject: string; relation: string; object: string; confidence: number; scope: string }[]
  memories: { id: string; content: string; tags: string; scope: string; created_at: number; decay_score: number }[]
}

const BASE = ''

export async function fetchStats(): Promise<Stats> {
  return (await fetch(`${BASE}/api/stats`)).json()
}

export async function fetchMemories(): Promise<Memory[]> {
  return (await fetch(`${BASE}/api/memories`)).json()
}

export async function fetchGraph(): Promise<GraphData> {
  return (await fetch(`${BASE}/api/graph`)).json()
}

export async function fetchEntity(name: string): Promise<EntityData> {
  return (await fetch(`${BASE}/api/entity?name=${encodeURIComponent(name)}`)).json()
}

export async function searchMemories(q: string): Promise<Memory[]> {
  return (await fetch(`${BASE}/api/search?q=${encodeURIComponent(q)}`)).json()
}
