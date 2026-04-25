import { X } from 'lucide-react'
import type { EntityData, Memory } from '@/lib/api'

interface EntityProps {
  name: string
  data: EntityData
  onClose: () => void
}

interface MemoryProps {
  memory: Memory
  onClose: () => void
}

function parseTags(raw: string): string[] {
  try { return JSON.parse(raw || '[]') } catch { return [] }
}

function formatDate(ts: number) {
  if (!ts) return ''
  return new Date(ts).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function EntityDetail({ name, data, onClose }: EntityProps) {
  return (
    <Panel title={name} onClose={onClose}>
      {data.facts.length > 0 && (
        <Section title={`Facts (${data.facts.length})`}>
          {data.facts.map((f, i) => (
            <div key={i} className="font-mono text-xs py-1 leading-relaxed">
              <span className="text-node-blue">{f.subject}</span>
              <span className="text-accent mx-1">&rarr;</span>
              <span className="text-text-dim">{f.relation}</span>
              <span className="text-accent mx-1">&rarr;</span>
              <span className="text-node-green">{f.object}</span>
            </div>
          ))}
        </Section>
      )}

      {data.memories.length > 0 && (
        <Section title={`Related Memories (${data.memories.length})`}>
          {data.memories.map(m => (
            <div key={m.id} className="text-sm leading-relaxed p-2.5 bg-bg rounded-lg mb-2">
              {m.content.substring(0, 250)}
              {m.content.length > 250 && '...'}
            </div>
          ))}
        </Section>
      )}

      {!data.facts.length && !data.memories.length && (
        <div className="p-6 text-center text-text-dim text-sm">No details found.</div>
      )}
    </Panel>
  )
}

export function MemoryDetail({ memory, onClose }: MemoryProps) {
  const tags = parseTags(memory.tags)

  return (
    <Panel title="Memory" onClose={onClose}>
      <Section title="Content">
        <div className="text-sm leading-relaxed p-3 bg-bg rounded-lg whitespace-pre-wrap">
          {memory.content}
        </div>
      </Section>

      {memory.summary && (
        <Section title="Summary">
          <div className="text-sm leading-relaxed p-3 bg-bg rounded-lg text-text-dim">
            {memory.summary}
          </div>
        </Section>
      )}

      <Section title="Metadata">
        <div className="grid grid-cols-2 gap-2 text-xs">
          <MetaItem label="Scope" value={memory.scope} />
          <MetaItem label="Decay" value={memory.decay_score.toFixed(3)} />
          <MetaItem label="Accessed" value={`${memory.access_count}x`} />
          <MetaItem label="Created" value={formatDate(memory.created_at)} />
        </div>
        {tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-3">
            {tags.map(t => (
              <span key={t} className="bg-bg border border-border rounded px-2 py-0.5 text-[10px] text-text-dim">{t}</span>
            ))}
          </div>
        )}
      </Section>
    </Panel>
  )
}

function Panel({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="absolute top-3 right-3 w-[360px] max-h-[calc(100%-24px)] bg-card border border-border rounded-xl overflow-y-auto shadow-2xl shadow-black/40">
      <div className="p-4 border-b border-border flex items-center justify-between sticky top-0 bg-card z-10">
        <h3 className="text-base font-bold text-accent truncate pr-4">{title}</h3>
        <button onClick={onClose} className="text-text-dim hover:text-text transition-colors p-1">
          <X size={16} />
        </button>
      </div>
      {children}
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="p-4 border-b border-border last:border-b-0">
      <h4 className="text-[11px] font-semibold uppercase tracking-wider text-text-dim mb-2">{title}</h4>
      {children}
    </div>
  )
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-text-dim">{label}: </span>
      <span className="font-mono text-text">{value}</span>
    </div>
  )
}
