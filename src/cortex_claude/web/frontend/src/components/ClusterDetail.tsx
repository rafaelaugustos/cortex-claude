import { useEffect, useState } from 'react'
import { ArrowLeft, Trash2 } from 'lucide-react'
import {
  fetchCluster,
  formatCount,
  formatDate,
  parseTags,
  type Cluster,
  type ClusterDetail as Detail,
  type Memory,
} from '@/lib/api'
import { GraphView } from '@/components/GraphView'

interface Props {
  cluster: Cluster
  onBack: () => void
  onSelectMemory: (m: Memory) => void
  onSelectEntity: (name: string) => void
  onCleanCluster: (cluster: Cluster) => void
}

export function ClusterDetail({
  cluster,
  onBack,
  onSelectMemory,
  onSelectEntity,
  onCleanCluster,
}: Props) {
  const [detail, setDetail] = useState<Detail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setDetail(null)
    setError(null)
    fetchCluster(cluster.id, cluster.scope)
      .then(setDetail)
      .catch((e) => setError(String(e)))
  }, [cluster.id, cluster.scope])

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 border-b border-border px-6 py-3">
        <button
          onClick={onBack}
          className="btn-ghost flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-text-dim"
        >
          <ArrowLeft size={13} /> Clusters
        </button>

        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-text">
            {cluster.label?.trim() || 'sem rótulo'}
          </p>
          <p className="font-mono text-[11px] text-text-mute">
            #{cluster.id} · {cluster.scope} · {formatCount(cluster.member_count)} memórias
          </p>
        </div>

        <button
          onClick={() => onCleanCluster(cluster)}
          className="btn-ghost flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-text-mute hover:text-text"
          title="Enviar este cluster para a limpeza"
        >
          <Trash2 size={13} /> Limpar cluster
        </button>
      </div>

      {error ? (
        <p className="p-6 text-sm text-magenta">Não consegui carregar: {error}</p>
      ) : !detail ? (
        <div className="flex flex-1 items-center justify-center text-sm text-text-mute">
          Montando o sub-grafo…
        </div>
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-[1fr_340px]">
          <div className="min-w-0 border-r border-border">
            <GraphView
              data={detail.graph}
              onSelectNode={(id) => id && onSelectEntity(id)}
              emptyLabel="Este cluster ainda não tem fatos extraídos."
            />
          </div>

          <div className="flex min-h-0 flex-col">
            <p className="eyebrow border-b border-border px-4 py-3">
              Memórias mais fortes
            </p>
            <div className="flex-1 overflow-y-auto p-2">
              {detail.memories.map((m) => (
                <MemoryRow key={m.id} memory={m} onClick={() => onSelectMemory(m)} />
              ))}
              {detail.memories.length === 0 && (
                <p className="p-4 text-xs text-text-mute">Nenhuma memória neste cluster.</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function MemoryRow({ memory, onClick }: { memory: Memory; onClick: () => void }) {
  const tags = parseTags(memory.tags)
  return (
    <button
      onClick={onClick}
      className="mb-1 w-full rounded-[10px] border border-transparent p-2.5 text-left transition-colors hover:border-border hover:bg-surface-2"
    >
      <p className="line-clamp-2 text-[13px] leading-snug text-text-dim">{memory.content}</p>
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[10px] text-text-mute">
        <span className="tnum font-mono">{formatDate(memory.created_at)}</span>
        <span className="tnum font-mono text-accent/70">{memory.decay_score.toFixed(2)}</span>
        {tags.slice(0, 2).map((t) => (
          <span key={t} className="rounded border border-border px-1 py-px">
            {t}
          </span>
        ))}
      </div>
    </button>
  )
}
