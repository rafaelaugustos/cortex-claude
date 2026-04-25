import { type Stats } from '@/lib/api'
import { Brain, GitFork, Database, HardDrive } from 'lucide-react'

function formatSize(bytes: number) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

export function Header({ stats }: { stats: Stats | null }) {
  return (
    <header className="h-14 bg-card border-b border-border flex items-center justify-between px-6">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-bold tracking-tight">
          corte<span className="text-accent">x</span>
        </h1>
        <span className="text-xs text-text-dim font-mono">memory dashboard</span>
      </div>

      {stats && (
        <div className="flex gap-6">
          <Stat icon={<Brain size={14} />} label="memories" value={stats.total_memories} />
          <Stat icon={<GitFork size={14} />} label="facts" value={stats.total_facts} />
          <Stat icon={<Database size={14} />} label="scopes" value={stats.scopes.length} />
          <Stat icon={<HardDrive size={14} />} label="storage" value={formatSize(stats.total_size)} />
        </div>
      )}
    </header>
  )
}

function Stat({ icon, label, value }: { icon: React.ReactNode; label: string; value: string | number }) {
  return (
    <div className="flex items-center gap-1.5 text-xs text-text-dim">
      {icon}
      <span>{label}</span>
      <span className="text-text font-semibold font-mono">{value}</span>
    </div>
  )
}
