import { Boxes, FileText, Trash2 } from 'lucide-react'
import { cn } from '@/lib/cn'
import { formatCount, type Overview } from '@/lib/api'

export type View = 'clusters' | 'memories' | 'cleanup'

interface Props {
  overview: Overview | null
  view: View
  scope: string
  tag: string | null
  onView: (v: View) => void
  onScope: (s: string) => void
  onTag: (t: string | null) => void
}

const NAV: { id: View; label: string; icon: typeof Boxes }[] = [
  { id: 'clusters', label: 'Clusters', icon: Boxes },
  { id: 'memories', label: 'Memórias', icon: FileText },
  { id: 'cleanup', label: 'Limpar', icon: Trash2 },
]

export function Sidebar({ overview, view, scope, tag, onView, onScope, onTag }: Props) {
  const scopes = overview?.scopes ?? []
  const tags = overview?.tags ?? []

  return (
    <aside className="flex w-64 flex-col overflow-hidden border-r border-border bg-surface">
      <nav className="flex flex-col gap-0.5 p-3">
        {NAV.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => onView(id)}
            className={cn(
              'flex items-center gap-2.5 rounded-[10px] px-3 py-2 text-sm transition-colors',
              view === id
                ? 'bg-surface-2 font-semibold text-text'
                : 'text-text-dim hover:bg-surface-2/60 hover:text-text',
            )}
          >
            <Icon size={15} className={view === id ? 'text-accent' : ''} />
            {label}
          </button>
        ))}
      </nav>

      <div className="flex-1 overflow-y-auto px-3 pb-4">
        <Section title="Escopos">
          <ScopeRow
            active={scope === 'all'}
            label="todos"
            count={overview?.totals.memories ?? 0}
            onClick={() => onScope('all')}
          />
          {scopes
            .filter((s) => s.memories > 0)
            .map((s) => (
              <ScopeRow
                key={s.name}
                active={scope === s.name}
                label={s.name.replace(/^project:/, '')}
                count={s.memories}
                onClick={() => onScope(s.name)}
              />
            ))}
          {scopes.some((s) => s.memories === 0) && (
            <p className="px-2 pt-1.5 text-[11px] text-text-mute">
              +{scopes.filter((s) => s.memories === 0).length} escopos vazios
            </p>
          )}
        </Section>

        {tags.length > 0 && (
          <Section title="Tags">
            <div className="flex flex-wrap gap-1">
              {tags.slice(0, 14).map((t) => (
                <button
                  key={t.name}
                  onClick={() => onTag(tag === t.name ? null : t.name)}
                  title={`${formatCount(t.count)} memórias`}
                  className={cn(
                    'rounded-md border px-1.5 py-0.5 text-[10px] transition-colors',
                    tag === t.name
                      ? 'border-accent bg-accent/15 text-accent'
                      : 'border-border text-text-mute hover:border-hairline hover:text-text-dim',
                  )}
                >
                  {t.name}
                </button>
              ))}
            </div>
          </Section>
        )}

        {overview && <Growth data={overview.growth} />}
      </div>
    </aside>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-4">
      <p className="eyebrow mb-2 px-2">{title}</p>
      <div className="flex flex-col gap-0.5">{children}</div>
    </div>
  )
}

function ScopeRow({
  active,
  label,
  count,
  onClick,
}: {
  active: boolean
  label: string
  count: number
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-xs transition-colors',
        active ? 'bg-surface-2 text-text' : 'text-text-dim hover:bg-surface-2/60 hover:text-text',
      )}
    >
      <span className="truncate" title={label}>
        {label}
      </span>
      <span className="tnum shrink-0 font-mono text-[10px] text-text-mute">
        {formatCount(count)}
      </span>
    </button>
  )
}

/* Thirty days of intake. Not a chart with axes — a pulse, to spot the day
   auto-capture ran away with itself. */
function Growth({ data }: { data: { day: number; count: number }[] }) {
  const max = Math.max(1, ...data.map((d) => d.count))
  const total = data.reduce((a, d) => a + d.count, 0)

  return (
    <div className="mt-5">
      <p className="eyebrow mb-2 px-2">Últimos 30 dias</p>
      <div className="flex h-10 items-end gap-[2px] px-2">
        {data.map((d) => (
          <div
            key={d.day}
            title={`${new Date(d.day).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' })}: ${d.count}`}
            className="flex-1 rounded-sm bg-accent/45 transition-colors hover:bg-accent"
            style={{ height: `${Math.max(2, (d.count / max) * 100)}%` }}
          />
        ))}
      </div>
      <p className="tnum mt-1.5 px-2 text-[11px] text-text-mute">
        {formatCount(total)} memórias no período
      </p>
    </div>
  )
}
