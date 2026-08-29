import { useEffect, useMemo, useRef, useState } from 'react'
import { Search } from 'lucide-react'
import { fetchClusters, formatCount, type Cluster } from '@/lib/api'
import { cn } from '@/lib/cn'

const PAGE = 60

interface Props {
  scope: string
  onOpen: (cluster: Cluster) => void
}

export function ClusterGrid({ scope, onOpen }: Props) {
  const [items, setItems] = useState<Cluster[]>([])
  const [total, setTotal] = useState(0)
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<'size' | 'recent'>('size')
  const [loading, setLoading] = useState(true)
  const reqId = useRef(0)

  useEffect(() => {
    const id = ++reqId.current
    setLoading(true)
    const timer = setTimeout(() => {
      fetchClusters({ scope, q: query || undefined, sort, limit: PAGE, offset: 0 })
        .then((page) => {
          if (reqId.current !== id) return
          setItems(page.items)
          setTotal(page.total)
        })
        .finally(() => reqId.current === id && setLoading(false))
    }, query ? 220 : 0)
    return () => clearTimeout(timer)
  }, [scope, query, sort])

  const loadMore = () => {
    fetchClusters({
      scope,
      q: query || undefined,
      sort,
      limit: PAGE,
      offset: items.length,
    }).then((page) => setItems((prev) => [...prev, ...page.items]))
  }

  const max = useMemo(() => Math.max(1, ...items.map((c) => c.member_count)), [items])

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 border-b border-border px-6 py-3">
        <div className="relative flex-1 max-w-md">
          <Search
            size={14}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-mute"
          />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filtrar clusters por assunto…"
            className="w-full rounded-[10px] border border-border bg-ink py-2 pl-9 pr-3 text-sm text-text outline-none transition-colors placeholder:text-text-mute focus:border-accent/60"
          />
        </div>

        <div className="flex gap-1">
          <Toggle active={sort === 'size'} onClick={() => setSort('size')}>
            Maiores
          </Toggle>
          <Toggle active={sort === 'recent'} onClick={() => setSort('recent')}>
            Recentes
          </Toggle>
        </div>

        <span className="tnum ml-auto font-mono text-xs text-text-mute">
          {formatCount(total)} clusters
        </span>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        {loading && items.length === 0 ? (
          <SkeletonGrid />
        ) : items.length === 0 ? (
          <p className="pt-16 text-center text-sm text-text-mute">
            Nenhum cluster corresponde a “{query}”.
          </p>
        ) : (
          <>
            <div className="grid grid-cols-[repeat(auto-fill,minmax(210px,1fr))] gap-3">
              {items.map((c, i) => (
                <ClusterCard
                  key={`${c.scope}-${c.id}`}
                  cluster={c}
                  max={max}
                  index={i}
                  onClick={() => onOpen(c)}
                />
              ))}
            </div>

            {items.length < total && (
              <div className="flex justify-center pt-6">
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

function ClusterCard({
  cluster,
  max,
  index,
  onClick,
}: {
  cluster: Cluster
  max: number
  index: number
  onClick: () => void
}) {
  const label = cluster.label?.trim() || 'sem rótulo'
  const share = (cluster.member_count / max) * 100

  return (
    <button
      onClick={onClick}
      className="panel panel-link reveal flex flex-col gap-2.5 p-4 text-left"
      style={{ animationDelay: `${Math.min(index, 24) * 12}ms` }}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="display tnum text-2xl text-text">{formatCount(cluster.member_count)}</span>
        <span className="font-mono text-[10px] text-text-mute">#{cluster.id}</span>
      </div>

      <p className="line-clamp-2 min-h-[2.4em] text-[13px] leading-snug text-text-dim">{label}</p>

      <div className="h-[3px] w-full overflow-hidden rounded-full bg-border">
        <div className="h-full rounded-full bg-accent/70" style={{ width: `${share}%` }} />
      </div>
    </button>
  )
}

function Toggle({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'rounded-[9px] px-3 py-1.5 text-xs transition-colors',
        active ? 'bg-accent/15 font-semibold text-accent' : 'text-text-mute hover:text-text-dim',
      )}
    >
      {children}
    </button>
  )
}

function SkeletonGrid() {
  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(210px,1fr))] gap-3">
      {Array.from({ length: 12 }).map((_, i) => (
        <div key={i} className="panel h-[104px] animate-pulse opacity-40" />
      ))}
    </div>
  )
}
