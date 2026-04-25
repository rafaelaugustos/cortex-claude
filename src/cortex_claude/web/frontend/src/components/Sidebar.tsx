import { useState } from 'react'
import { Search } from 'lucide-react'
import { cn } from '@/lib/cn'
import type { Memory, GraphData } from '@/lib/api'

interface Props {
  memories: Memory[]
  facts: GraphData['edges']
  onSearch: (q: string) => void
  onSelectMemory: (id: string) => void
  onFocusNode: (id: string) => void
}

function formatDate(ts: number) {
  if (!ts) return ''
  return new Date(ts).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function parseTags(raw: string): string[] {
  try { return JSON.parse(raw || '[]') } catch { return [] }
}

export function Sidebar({ memories, facts, onSearch, onSelectMemory, onFocusNode }: Props) {
  const [tab, setTab] = useState<'memories' | 'facts'>('memories')

  return (
    <aside className="w-80 bg-card border-r border-border flex flex-col overflow-hidden">
      <div className="p-3 border-b border-border">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-dim" />
          <input
            type="text"
            placeholder="Search memories..."
            onChange={e => onSearch(e.target.value)}
            className="w-full bg-bg border border-border rounded-lg py-2 pl-9 pr-3 text-sm text-text placeholder:text-text-dim outline-none focus:border-accent focus:ring-1 focus:ring-accent/20 transition-colors"
          />
        </div>
      </div>

      <div className="flex border-b border-border">
        <TabButton active={tab === 'memories'} onClick={() => setTab('memories')}>
          Memories ({memories.length})
        </TabButton>
        <TabButton active={tab === 'facts'} onClick={() => setTab('facts')}>
          Facts ({facts.length})
        </TabButton>
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        {tab === 'memories' ? (
          memories.length === 0 ? (
            <Empty>No memories yet.</Empty>
          ) : (
            memories.map(m => (
              <MemoryItem key={m.id} memory={m} onClick={() => onSelectMemory(m.id)} />
            ))
          )
        ) : (
          facts.length === 0 ? (
            <Empty>No facts extracted yet.</Empty>
          ) : (
            facts.map((f, i) => (
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

function MemoryItem({ memory, onClick }: { memory: Memory; onClick: () => void }) {
  const tags = parseTags(memory.tags)
  return (
    <div
      onClick={onClick}
      className="p-2.5 rounded-lg cursor-pointer mb-1 border border-transparent hover:bg-card-hover hover:border-border transition-colors"
    >
      <p className="text-sm leading-snug line-clamp-2">{memory.content}</p>
      <div className="flex gap-2 mt-1.5 text-[11px] text-text-dim items-center flex-wrap">
        <span className="font-mono">{memory.scope}</span>
        <span>{formatDate(memory.created_at)}</span>
        {tags.slice(0, 3).map(t => (
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
