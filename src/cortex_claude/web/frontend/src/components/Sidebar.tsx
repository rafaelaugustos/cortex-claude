import { useState, useMemo } from 'react'
import { Search, SlidersHorizontal, X, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/cn'
import type { Memory, GraphData } from '@/lib/api'

interface Props {
  memories: Memory[]
  facts: GraphData['edges']
  scopes: string[]
  onSearch: (q: string) => void
  onSelectMemory: (id: string) => void
  onFocusNode: (id: string) => void
}

type SortKey = 'date' | 'score' | 'accessed'

function formatDate(ts: number) {
  if (!ts) return ''
  return new Date(ts).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function parseTags(raw: string): string[] {
  try { return JSON.parse(raw || '[]') } catch { return [] }
}

export function Sidebar({ memories, facts, scopes, onSearch, onSelectMemory, onFocusNode }: Props) {
  const [tab, setTab] = useState<'memories' | 'facts'>('memories')
  const [searchQuery, setSearchQuery] = useState('')
  const [showFilters, setShowFilters] = useState(false)
  const [selectedScope, setSelectedScope] = useState<string>('all')
  const [selectedTag, setSelectedTag] = useState<string | null>(null)
  const [sortBy, setSortBy] = useState<SortKey>('date')

  const allTags = useMemo(() => {
    const tags = new Set<string>()
    memories.forEach(m => parseTags(m.tags).forEach(t => tags.add(t)))
    return Array.from(tags).sort()
  }, [memories])

  const filteredMemories = useMemo(() => {
    let result = [...memories]

    if (selectedScope !== 'all') {
      result = result.filter(m => m.scope === selectedScope)
    }

    if (selectedTag) {
      result = result.filter(m => parseTags(m.tags).includes(selectedTag))
    }

    if (sortBy === 'score') {
      result.sort((a, b) => b.decay_score - a.decay_score)
    } else if (sortBy === 'accessed') {
      result.sort((a, b) => b.accessed_at - a.accessed_at)
    } else {
      result.sort((a, b) => b.created_at - a.created_at)
    }

    return result
  }, [memories, selectedScope, selectedTag, sortBy])

  const filteredFacts = useMemo(() => {
    if (!searchQuery || searchQuery.length < 2) return facts
    const q = searchQuery.toLowerCase()
    return facts.filter(f =>
      f.source.includes(q) || f.target.includes(q) || f.label.includes(q)
    )
  }, [facts, searchQuery])

  const activeFilters = (selectedScope !== 'all' ? 1 : 0) + (selectedTag ? 1 : 0) + (sortBy !== 'date' ? 1 : 0)

  return (
    <aside className="w-80 bg-card border-r border-border flex flex-col overflow-hidden">
      {/* Search */}
      <div className="p-3 border-b border-border">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-dim" />
          <input
            type="text"
            placeholder={tab === 'memories' ? 'Search memories...' : 'Filter facts...'}
            value={searchQuery}
            onChange={e => {
              setSearchQuery(e.target.value)
              if (tab === 'memories') onSearch(e.target.value)
            }}
            className="w-full bg-bg border border-border rounded-lg py-2 pl-9 pr-9 text-sm text-text placeholder:text-text-dim outline-none focus:border-accent focus:ring-1 focus:ring-accent/20 transition-colors"
          />
          {tab === 'memories' && (
            <button
              onClick={() => setShowFilters(!showFilters)}
              className={cn(
                'absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded transition-colors',
                showFilters || activeFilters > 0 ? 'text-accent' : 'text-text-dim hover:text-text'
              )}
            >
              <SlidersHorizontal size={14} />
              {activeFilters > 0 && (
                <span className="absolute -top-1 -right-1 w-3.5 h-3.5 bg-accent rounded-full text-[8px] text-white flex items-center justify-center font-bold">
                  {activeFilters}
                </span>
              )}
            </button>
          )}
        </div>
      </div>

      {/* Filters panel */}
      {showFilters && tab === 'memories' && (
        <div className="border-b border-border p-3 space-y-3 bg-bg/50">
          {/* Scope filter */}
          <div>
            <label className="text-[10px] font-semibold uppercase tracking-wider text-text-dim block mb-1">Scope</label>
            <div className="relative">
              <select
                value={selectedScope}
                onChange={e => setSelectedScope(e.target.value)}
                className="w-full bg-bg border border-border rounded-md py-1.5 px-2.5 text-xs text-text appearance-none outline-none focus:border-accent cursor-pointer"
              >
                <option value="all">All scopes</option>
                {scopes.map(s => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
              <ChevronDown size={12} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-dim pointer-events-none" />
            </div>
          </div>

          {/* Sort */}
          <div>
            <label className="text-[10px] font-semibold uppercase tracking-wider text-text-dim block mb-1">Sort by</label>
            <div className="flex gap-1">
              <SortBtn active={sortBy === 'date'} onClick={() => setSortBy('date')}>Newest</SortBtn>
              <SortBtn active={sortBy === 'score'} onClick={() => setSortBy('score')}>Relevance</SortBtn>
              <SortBtn active={sortBy === 'accessed'} onClick={() => setSortBy('accessed')}>Last used</SortBtn>
            </div>
          </div>

          {/* Tags */}
          {allTags.length > 0 && (
            <div>
              <label className="text-[10px] font-semibold uppercase tracking-wider text-text-dim block mb-1">Tags</label>
              <div className="flex flex-wrap gap-1 max-h-20 overflow-y-auto">
                {allTags.map(t => (
                  <button
                    key={t}
                    onClick={() => setSelectedTag(selectedTag === t ? null : t)}
                    className={cn(
                      'px-2 py-0.5 rounded text-[10px] border transition-colors',
                      selectedTag === t
                        ? 'bg-accent/20 border-accent text-accent'
                        : 'bg-bg border-border text-text-dim hover:text-text hover:border-text-dim'
                    )}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Clear filters */}
          {activeFilters > 0 && (
            <button
              onClick={() => { setSelectedScope('all'); setSelectedTag(null); setSortBy('date') }}
              className="flex items-center gap-1 text-[10px] text-accent hover:text-accent-dim transition-colors"
            >
              <X size={10} /> Clear all filters
            </button>
          )}
        </div>
      )}

      {/* Tabs */}
      <div className="flex border-b border-border">
        <TabButton active={tab === 'memories'} onClick={() => setTab('memories')}>
          Memories ({filteredMemories.length})
        </TabButton>
        <TabButton active={tab === 'facts'} onClick={() => setTab('facts')}>
          Facts ({filteredFacts.length})
        </TabButton>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto p-2">
        {tab === 'memories' ? (
          filteredMemories.length === 0 ? (
            <Empty>{activeFilters > 0 ? 'No memories match filters.' : 'No memories yet.'}</Empty>
          ) : (
            filteredMemories.map(m => (
              <MemoryItem key={m.id} memory={m} onClick={() => onSelectMemory(m.id)} />
            ))
          )
        ) : (
          filteredFacts.length === 0 ? (
            <Empty>No facts {searchQuery ? 'match your search.' : 'extracted yet.'}</Empty>
          ) : (
            filteredFacts.map((f, i) => (
              <FactItem key={i} fact={f} onClick={() => onFocusNode(f.source)} />
            ))
          )
        )}
      </div>
    </aside>
  )
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'flex-1 py-2.5 text-xs font-semibold uppercase tracking-wider border-b-2 transition-colors',
        active ? 'text-accent border-accent' : 'text-text-dim border-transparent hover:text-text hover:bg-card-hover'
      )}
    >
      {children}
    </button>
  )
}

function SortBtn({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'px-2.5 py-1 rounded-md text-[10px] font-medium transition-colors',
        active ? 'bg-accent/20 text-accent' : 'bg-bg text-text-dim hover:text-text'
      )}
    >
      {children}
    </button>
  )
}

function MemoryItem({ memory, onClick }: { memory: Memory; onClick: () => void }) {
  const tags = parseTags(memory.tags)
  return (
    <div
      onClick={onClick}
      className="p-2.5 rounded-lg cursor-pointer mb-1 border border-transparent hover:bg-card-hover hover:border-border transition-colors"
    >
      <p className="text-sm leading-snug line-clamp-2">{memory.content}</p>
      <div className="flex gap-2 mt-1.5 text-[11px] text-text-dim items-center flex-wrap">
        <span className="font-mono text-[10px] bg-bg border border-border rounded px-1.5 py-0.5">{memory.scope}</span>
        <span>{formatDate(memory.created_at)}</span>
        <span className="font-mono text-accent/60">{memory.decay_score.toFixed(2)}</span>
        {tags.slice(0, 2).map(t => (
          <span key={t} className="bg-bg border border-border rounded px-1.5 py-0.5 text-[10px]">{t}</span>
        ))}
      </div>
    </div>
  )
}

function FactItem({ fact, onClick }: { fact: GraphData['edges'][0]; onClick: () => void }) {
  return (
    <div
      onClick={onClick}
      className="py-1.5 px-2.5 rounded-md cursor-pointer mb-0.5 hover:bg-card-hover font-mono text-xs transition-colors"
    >
      <span className="text-node-blue">{fact.source}</span>
      <span className="text-accent mx-1">&rarr;</span>
      <span className="text-text-dim">{fact.label}</span>
      <span className="text-accent mx-1">&rarr;</span>
      <span className="text-node-green">{fact.target}</span>
    </div>
  )
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-center h-40 text-text-dim text-sm text-center px-6">
      {children}
    </div>
  )
}
