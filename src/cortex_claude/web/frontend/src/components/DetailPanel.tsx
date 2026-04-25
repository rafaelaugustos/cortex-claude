import { useState } from 'react'
import { X, Trash2, Pencil, Check, XCircle } from 'lucide-react'
import type { EntityData, Memory } from '@/lib/api'
import { deleteMemory, updateMemory } from '@/lib/api'

interface EntityProps {
  name: string
  data: EntityData
  onClose: () => void
}

interface MemoryProps {
  memory: Memory
  onClose: () => void
  onDeleted: (id: string) => void
  onUpdated: (id: string, content: string, tags: string[]) => void
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

export function MemoryDetail({ memory, onClose, onDeleted, onUpdated }: MemoryProps) {
  const [editing, setEditing] = useState(false)
  const [editContent, setEditContent] = useState(memory.content)
  const [editTags, setEditTags] = useState(parseTags(memory.tags).join(', '))
  const [confirmDelete, setConfirmDelete] = useState(false)
  const tags = parseTags(memory.tags)

  const handleSave = async () => {
    const newTags = editTags.split(',').map(t => t.trim()).filter(Boolean)
    const res = await updateMemory(memory.id, { content: editContent, tags: newTags })
    if (res.ok) {
      onUpdated(memory.id, editContent, newTags)
      setEditing(false)
    }
  }

  const handleDelete = async () => {
    const res = await deleteMemory(memory.id)
    if (res.ok) {
      onDeleted(memory.id)
    }
  }

  return (
    <Panel title="Memory" onClose={onClose} actions={
      <div className="flex gap-1">
        {!editing && (
          <button onClick={() => setEditing(true)} className="p-1.5 rounded-md text-text-dim hover:text-node-blue hover:bg-node-blue/10 transition-colors" title="Edit">
            <Pencil size={13} />
          </button>
        )}
        <button
          onClick={() => setConfirmDelete(true)}
          className="p-1.5 rounded-md text-text-dim hover:text-red-400 hover:bg-red-400/10 transition-colors"
          title="Delete"
        >
          <Trash2 size={13} />
        </button>
      </div>
    }>
      {/* Delete confirmation */}
      {confirmDelete && (
        <div className="p-4 bg-red-500/5 border-b border-red-500/20">
          <p className="text-sm text-red-400 mb-3">Delete this memory and all its facts?</p>
          <div className="flex gap-2">
            <button
              onClick={handleDelete}
              className="px-3 py-1.5 rounded-md bg-red-500/20 text-red-400 text-xs font-medium hover:bg-red-500/30 transition-colors"
            >
              Delete
            </button>
            <button
              onClick={() => setConfirmDelete(false)}
              className="px-3 py-1.5 rounded-md bg-bg text-text-dim text-xs hover:text-text transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      <Section title="Content">
        {editing ? (
          <div className="space-y-2">
            <textarea
              value={editContent}
              onChange={e => setEditContent(e.target.value)}
              className="w-full bg-bg border border-border rounded-lg p-3 text-sm text-text resize-none outline-none focus:border-accent min-h-[120px] font-mono"
              rows={6}
            />
            <div>
              <label className="text-[10px] font-semibold uppercase tracking-wider text-text-dim block mb-1">Tags (comma separated)</label>
              <input
                value={editTags}
                onChange={e => setEditTags(e.target.value)}
                className="w-full bg-bg border border-border rounded-md py-1.5 px-2.5 text-xs text-text outline-none focus:border-accent"
                placeholder="tag1, tag2, tag3"
              />
            </div>
            <div className="flex gap-2 pt-1">
              <button
                onClick={handleSave}
                className="flex items-center gap-1 px-3 py-1.5 rounded-md bg-accent/20 text-accent text-xs font-medium hover:bg-accent/30 transition-colors"
              >
                <Check size={12} /> Save
              </button>
              <button
                onClick={() => { setEditing(false); setEditContent(memory.content); setEditTags(tags.join(', ')) }}
                className="flex items-center gap-1 px-3 py-1.5 rounded-md bg-bg text-text-dim text-xs hover:text-text transition-colors"
              >
                <XCircle size={12} /> Cancel
              </button>
            </div>
          </div>
        ) : (
          <div className="text-sm leading-relaxed p-3 bg-bg rounded-lg whitespace-pre-wrap">
            {memory.content}
          </div>
        )}
      </Section>

      {memory.summary && !editing && (
        <Section title="Summary">
          <div className="text-sm leading-relaxed p-3 bg-bg rounded-lg text-text-dim">
            {memory.summary}
          </div>
        </Section>
      )}

      {!editing && (
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
      )}
    </Panel>
  )
}

function Panel({ title, onClose, actions, children }: { title: string; onClose: () => void; actions?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="absolute top-3 right-3 w-[360px] max-h-[calc(100%-24px)] bg-card border border-border rounded-xl overflow-y-auto shadow-2xl shadow-black/40">
      <div className="p-4 border-b border-border flex items-center justify-between sticky top-0 bg-card z-10">
        <h3 className="text-base font-bold text-accent truncate pr-4">{title}</h3>
        <div className="flex items-center gap-1">
          {actions}
          <button onClick={onClose} className="text-text-dim hover:text-text transition-colors p-1 ml-1">
            <X size={16} />
          </button>
        </div>
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
