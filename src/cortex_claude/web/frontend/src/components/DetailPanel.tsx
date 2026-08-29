import { useEffect, useState } from 'react'
import { Check, Pencil, Trash2, X } from 'lucide-react'
import {
  deleteMemory,
  fetchEntity,
  fetchMemory,
  formatCount,
  formatDateTime,
  formatSize,
  parseTags,
  updateMemory,
  type Fact,
  type Memory,
} from '@/lib/api'
import { GraphView } from '@/components/GraphView'

function Shell({
  title,
  subtitle,
  onClose,
  children,
  wide,
}: {
  title: string
  subtitle?: string
  onClose: () => void
  children: React.ReactNode
  wide?: boolean
}) {
  return (
    <div
      className="reveal absolute inset-y-0 right-0 z-30 flex flex-col border-l border-border bg-surface shadow-[-24px_0_60px_-30px_rgba(0,0,0,0.9)]"
      style={{ width: wide ? 620 : 440 }}
    >
      <div className="flex items-start gap-3 border-b border-border px-4 py-3">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-text" title={title}>
            {title}
          </p>
          {subtitle && <p className="font-mono text-[11px] text-text-mute">{subtitle}</p>}
        </div>
        <button
          onClick={onClose}
          className="shrink-0 rounded-md p-1 text-text-mute transition-colors hover:bg-surface-2 hover:text-text"
        >
          <X size={15} />
        </button>
      </div>
      {children}
    </div>
  )
}

// ── Memory ───────────────────────────────────────────────────

export function MemoryPanel({
  memory,
  onClose,
  onChanged,
}: {
  memory: Memory
  onClose: () => void
  onChanged: () => void
}) {
  const [facts, setFacts] = useState<Fact[]>([])
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(memory.content)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setEditing(false)
    setConfirming(false)
    setDraft(memory.content)
    setFacts([])
    fetchMemory(memory.id)
      .then((r) => setFacts(r.facts ?? []))
      .catch(() => setFacts([]))
  }, [memory.id, memory.content])

  const save = async () => {
    setBusy(true)
    try {
      await updateMemory(memory.id, { content: draft })
      setEditing(false)
      onChanged()
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    setBusy(true)
    try {
      await deleteMemory(memory.id)
      onChanged()
      onClose()
    } finally {
      setBusy(false)
    }
  }

  const tags = parseTags(memory.tags)

  return (
    <Shell
      title="Memória"
      subtitle={`${memory._scope} · ${formatDateTime(memory.created_at)} · ${formatSize(memory.size)}`}
      onClose={onClose}
    >
      <div className="flex-1 overflow-y-auto p-4">
        {editing ? (
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={14}
            className="w-full resize-y rounded-[10px] border border-border bg-ink p-3 font-mono text-[12px] leading-relaxed text-text outline-none focus:border-accent/60"
          />
        ) : (
          <p className="whitespace-pre-wrap break-words text-[13px] leading-relaxed text-text-dim">
            {memory.content}
          </p>
        )}

        <div className="mt-4 flex flex-wrap gap-1.5">
          {tags.map((t) => (
            <span
              key={t}
              className="rounded-md border border-border px-1.5 py-0.5 text-[10px] text-text-mute"
            >
              {t}
            </span>
          ))}
        </div>

        <div className="mt-5 grid grid-cols-3 gap-2">
          <Metric label="relevância" value={memory.decay_score.toFixed(2)} />
          <Metric label="acessos" value={String(memory.access_count)} />
          <Metric label="cluster" value={memory.cluster_id ? `#${memory.cluster_id}` : '—'} />
        </div>

        {facts.length > 0 && (
          <div className="mt-5">
            <p className="eyebrow mb-2">{facts.length} fatos extraídos</p>
            <div className="flex flex-col gap-0.5">
              {facts.map((f, i) => (
                <FactRow key={i} fact={f} />
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="flex items-center gap-2 border-t border-border p-3">
        {editing ? (
          <>
            <button onClick={save} disabled={busy} className="btn-accent px-3 py-1.5 text-xs">
              <span className="flex items-center gap-1.5">
                <Check size={13} /> Salvar
              </span>
            </button>
            <button
              onClick={() => {
                setEditing(false)
                setDraft(memory.content)
              }}
              className="btn-ghost px-3 py-1.5 text-xs text-text-dim"
            >
              Cancelar
            </button>
          </>
        ) : confirming ? (
          <>
            <span className="flex-1 text-xs text-text-dim">Apagar de vez?</span>
            <button onClick={remove} disabled={busy} className="btn-danger px-3 py-1.5 text-xs">
              Apagar
            </button>
            <button
              onClick={() => setConfirming(false)}
              className="btn-ghost px-3 py-1.5 text-xs text-text-dim"
            >
              Não
            </button>
          </>
        ) : (
          <>
            <button
              onClick={() => setEditing(true)}
              className="btn-ghost px-3 py-1.5 text-xs text-text-dim"
            >
              <span className="flex items-center gap-1.5">
                <Pencil size={13} /> Editar
              </span>
            </button>
            <button
              onClick={() => setConfirming(true)}
              className="btn-ghost ml-auto px-3 py-1.5 text-xs text-text-mute hover:text-magenta"
            >
              <span className="flex items-center gap-1.5">
                <Trash2 size={13} /> Apagar
              </span>
            </button>
          </>
        )}
      </div>
    </Shell>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="panel px-2.5 py-2">
      <p className="display tnum text-base text-text">{value}</p>
      <p className="eyebrow text-[9px]">{label}</p>
    </div>
  )
}

function FactRow({ fact }: { fact: Fact }) {
  return (
    <div className="rounded-md px-2 py-1 font-mono text-[11px] leading-relaxed transition-colors hover:bg-surface-2">
      <span className="text-cyan">{fact.subject}</span>
      <span className="mx-1 text-text-mute">→</span>
      <span className="text-text-dim">{fact.relation}</span>
      <span className="mx-1 text-text-mute">→</span>
      <span className="text-teal">{fact.object}</span>
    </div>
  )
}

// ── Entity ───────────────────────────────────────────────────

export function EntityPanel({
  name,
  onClose,
  onSelectMemory,
  onSelectEntity,
}: {
  name: string
  onClose: () => void
  onSelectMemory: (m: Memory) => void
  onSelectEntity: (n: string) => void
}) {
  const [data, setData] = useState<Awaited<ReturnType<typeof fetchEntity>> | null>(null)

  useEffect(() => {
    setData(null)
    fetchEntity(name).then(setData).catch(() => setData(null))
  }, [name])

  return (
    <Shell
      title={name}
      subtitle={data ? `${formatCount(data.facts.length)} fatos · ${data.memories.length} memórias` : 'carregando…'}
      onClose={onClose}
      wide
    >
      {!data ? (
        <div className="flex flex-1 items-center justify-center text-sm text-text-mute">
          Carregando entidade…
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="h-[42%] shrink-0 border-b border-border">
            <GraphView
              data={data.graph}
              onSelectNode={(id) => id && id !== name && onSelectEntity(id)}
              emptyLabel="Sem conexões para esta entidade."
            />
          </div>

          <div className="flex-1 overflow-y-auto p-3">
            <p className="eyebrow mb-2">Fatos</p>
            <div className="mb-4 flex flex-col gap-0.5">
              {data.facts.slice(0, 40).map((f, i) => (
                <FactRow key={i} fact={f} />
              ))}
            </div>

            <p className="eyebrow mb-2">Memórias que mencionam</p>
            {data.memories.map((m) => (
              <button
                key={m.id}
                onClick={() => onSelectMemory(m)}
                className="mb-1 w-full rounded-[10px] border border-transparent p-2.5 text-left transition-colors hover:border-border hover:bg-surface-2"
              >
                <p className="line-clamp-2 text-[12px] leading-snug text-text-dim">{m.content}</p>
                <p className="mt-1 font-mono text-[10px] text-text-mute">
                  {m._scope} · {formatDateTime(m.created_at)}
                </p>
              </button>
            ))}
          </div>
        </div>
      )}
    </Shell>
  )
}
