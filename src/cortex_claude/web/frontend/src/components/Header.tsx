import { formatCount, formatSize, type Overview } from '@/lib/api'

export function Header({ overview }: { overview: Overview | null }) {
  return (
    <header className="flex h-16 items-center justify-between border-b border-border bg-surface px-6">
      <div className="flex items-baseline gap-3">
        <div className="flex items-center gap-2.5">
          <Mark />
          <span className="display text-[19px]">cortex</span>
        </div>
        <span className="eyebrow">memória</span>
      </div>

      {overview && (
        <div className="flex items-center gap-7">
          <Stat label="memórias" value={formatCount(overview.totals.memories)} />
          <Stat label="fatos" value={formatCount(overview.totals.facts)} />
          <Stat label="clusters" value={formatCount(overview.totals.clusters)} />
          <Stat label="em disco" value={formatSize(overview.totals.size)} />
        </div>
      )}
    </header>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col items-end leading-tight">
      <span className="display tnum text-[15px] text-text">{value}</span>
      <span className="eyebrow text-[9px]">{label}</span>
    </div>
  )
}

function Mark() {
  return (
    <svg width="20" height="22" viewBox="0 0 20 22" fill="none" aria-hidden>
      <path
        d="M10 1 18.66 6v10L10 21 1.34 16V6L10 1Z"
        stroke="var(--color-accent)"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
      <circle cx="10" cy="11" r="2.6" fill="var(--color-accent)" />
    </svg>
  )
}
