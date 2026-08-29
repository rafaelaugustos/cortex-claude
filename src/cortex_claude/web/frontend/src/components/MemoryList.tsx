import { useEffect, useRef, useState } from 'react'
import { Search, X } from 'lucide-react'
import {
  fetchMemories,
  formatCount,
  formatDateTime,
  formatSize,
  parseTags,
  type Memory,
} from '@/lib/api'
import { cn } from '@/lib/cn'

const PAGE = 50

const SORTS = [
  { id: 'recent', label: 'Recentes' },
  { id: 'relevance', label: 'Relevância' },
  { id: 'accessed', label: 'Último uso' },
  { id: 'largest', label: 'Maiores' },
] as const

interface Props {
  scope: string
  tag: string | null
  onClearTag: () => void
  onSelect: (m: Memory) => void
  selectedId?: string | null
  refreshKey: number
}

export function MemoryList({
  scope,
  tag,
  onClearTag,
  onSelect,
  selectedId,
  refreshKey,
}: Props) {
  const [items, setItems] = useState<Memory[]>([])
  const [total, setTotal] = useState(0)
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<string>('recent')
  const [loading, setLoading] = useState(true)
  const reqId = useRef(0)

  useEffect(() => {
    const id = ++reqId.current
    setLoading(true)
    const timer = setTimeout(
      () => {
        fetchMemories({
          scope,
          tag: tag ?? undefined,
          q: query || undefined,
          sort,
          limit: PAGE,
          offset: 0,
        })
          .then((page) => {
            if (reqId.current !== id) return
            setItems(page.items)
            setTotal(page.total)
          })
          .finally(() => reqId.current === id && setLoading(false))
      },
      query ? 250 : 0,
    )
    return () => clearTimeout(timer)
  }, [scope, tag, query, sort, refreshKey])

  const loadMore = () => {
    fetchMemories({
      scope,
      tag: tag ?? undefined,
      q: query || undefined,
      sort,
      limit: PAGE,
      offset: items.length,
    }).then((page) => setItems((prev) => [...prev, ...page.items]))
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 border-b border-border px-6 py-3">
        <div className="relative max-w-md flex-1">
          <Search
            size={14}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-mute"
          />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Buscar no conteúdo das memórias…"
            className="w-full rounded-[10px] border border-border bg-ink py-2 pl-9 pr-3 text-sm text-text outline-none transition-colors placeholder:text-text-mute focus:border-accent/60"
          />
        </div>

        {tag && (
          <button
            onClick={onClearTag}
            className="flex items-center gap-1 rounded-md border border-accent bg-accent/15 px-2 py-1 text-[11px] text-accent"
          >
            {tag} <X size={11} />
          </button>
        )}

        <div className="flex gap-1">
          {SORTS.map((s) => (
            <button
              key={s.id}
              onClick={() => setSort(s.id)}
              className={cn(
                'rounded-[9px] px-2.5 py-1.5 text-xs transition-colors',
                sort === s.id
                  ? 'bg-accent/15 font-semibold text-accent'
                  : 'text-text-mute hover:text-text-dim',
              )}
            >
              {s.label}
            </button>
          ))}
        </div>

        <span className="tnum ml-auto shrink-0 font-mono text-xs text-text-mute">
          {formatCount(total)}
        </span>
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {loading && items.length === 0 ? (
          <div className="flex flex-col gap-2">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="panel h-[72px] animate-pulse opacity-40" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <p className="pt-16 text-center text-sm text-text-mute">
            Nenhuma memória encontrada com esses filtros.
          </p>
        ) : (
          <>
            {items.map((m) => (
              <Row
                key={`${m._scope}-${m.id}`}
                memory={m}
                active={selectedId === m.id}
                onClick={() => onSelect(m)}
              />
            ))}

            {items.length < total && (
              <div className="flex justify-center py-5">
                <button onClick={loadMore} className="btn-ghost px-5 py-2 text-sm text-text-dim">
                  Carregar mais ({formatCount(total - items.length)} restantes)
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function Row({
  memory,
  active,
  onClick,
}: {
  memory: Memory
  active: boolean
  onClick: () => void
}) {
  const tags = parseTags(memory.tags)
  return (
    <button
      onClick={onClick}
      className={cn(
        'mb-1.5 w-full rounded-[12px] border p-3 text-left transition-colors',
        active
          ? 'border-accent/50 bg-accent/[0.06]'
          : 'border-transparent hover:border-border hover:bg-surface',
      )}
    >
      <p className="line-clamp-2 text-[13px] leading-snug text-text-dim">{memory.content}</p>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] text-text-mute">
        <span className="rounded border border-border px-1.5 py-px font-mono">
          {memory._scope.replace(/^project:/, '')}
        </span>
        <span className="tnum font-mono">{formatDateTime(memory.created_at)}</span>
        <span className="tnum font-mono">{formatSize(memory.size)}</span>
        <span className="tnum font-mono text-accent/70">{memory.decay_score.toFixed(2)}</span>
        {tags.map((t) => (
          <span key={t} className="rounded border border-border px-1.5 py-px">
            {t}
          </span>
        ))}
      </div>
    </button>
  )
}
