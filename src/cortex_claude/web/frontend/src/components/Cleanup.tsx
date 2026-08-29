import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Plus, X } from 'lucide-react'
import {
  executeCleanup,
  formatCount,
  formatDateTime,
  formatSize,
  previewCleanup,
  type CleanupPreview,
  type CleanupRule,
  type Overview,
} from '@/lib/api'
import { cn } from '@/lib/cn'

interface Props {
  overview: Overview | null
  seedRules: CleanupRule[]
  onSeedConsumed: () => void
  onDone: () => void
}

function ruleKey(r: CleanupRule): string {
  return `${r.type}:${r.value}`
}

function ruleLabel(r: CleanupRule): string {
  switch (r.type) {
    case 'tag':
      return `tag “${r.value}”`
    case 'cluster':
      return `cluster #${r.value}`
    case 'scope':
      return `escopo “${r.value}”`
    case 'pattern':
      return `padrão /${r.value}/`
  }
}

export function Cleanup({ overview, seedRules, onSeedConsumed, onDone }: Props) {
  const [selected, setSelected] = useState<CleanupRule[]>([])
  const [pattern, setPattern] = useState('')
  const [preview, setPreview] = useState<CleanupPreview | null>(null)
  const [loading, setLoading] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [result, setResult] = useState<string | null>(null)

  useEffect(() => {
    if (!seedRules.length) return
    setSelected((prev) => {
      const keys = new Set(prev.map(ruleKey))
      return [...prev, ...seedRules.filter((r) => !keys.has(ruleKey(r)))]
    })
    onSeedConsumed()
  }, [seedRules, onSeedConsumed])

  const candidates = useMemo<CleanupRule[]>(() => {
    if (!overview) return []
    const tags: CleanupRule[] = overview.tags
      .filter((t) => t.name !== 'auto-capture')
      .slice(0, 12)
      .map((t) => ({ type: 'tag', value: t.name }))
    const scopes: CleanupRule[] = overview.scopes
      .filter((s) => s.memories > 0 && s.name !== 'global')
      .map((s) => ({ type: 'scope', value: s.name }))
    return [...tags, ...scopes]
  }, [overview])

  const counts = useMemo(() => {
    const map = new Map<string, number>()
    overview?.tags.forEach((t) => map.set(`tag:${t.name}`, t.count))
    overview?.scopes.forEach((s) => map.set(`scope:${s.name}`, s.memories))
    return map
  }, [overview])

  const toggle = (rule: CleanupRule) => {
    setPreview(null)
    setConfirming(false)
    setResult(null)
    setSelected((prev) => {
      const key = ruleKey(rule)
      return prev.some((r) => ruleKey(r) === key)
        ? prev.filter((r) => ruleKey(r) !== key)
        : [...prev, rule]
    })
  }

  const addPattern = () => {
    const value = pattern.trim()
    if (!value) return
    toggle({ type: 'pattern', value })
    setPattern('')
  }

  const runPreview = useCallback(async () => {
    if (!selected.length) return
    setLoading(true)
    setConfirming(false)
    setResult(null)
    try {
      setPreview(await previewCleanup(selected))
    } finally {
      setLoading(false)
    }
  }, [selected])

  const runDelete = async () => {
    setLoading(true)
    try {
      const r = await executeCleanup(selected)
      setResult(`${formatCount(r.deleted)} memórias apagadas.`)
      setSelected([])
      setPreview(null)
      setConfirming(false)
      onDone()
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="grid h-full grid-cols-[1fr_380px] overflow-hidden">
      <div className="overflow-y-auto p-6">
        <h2 className="display text-xl text-text">Limpar memória</h2>
        <p className="mt-1.5 max-w-xl text-[13px] leading-relaxed text-text-dim">
          Escolha o que remover. As regras somam — uma memória que bata em qualquer uma
          delas entra na conta. Nada é apagado antes de você ver a prévia.
        </p>

        <p className="eyebrow mb-2.5 mt-7">Por tag e escopo</p>
        <div className="flex flex-wrap gap-1.5">
          {candidates.map((rule) => {
            const active = selected.some((r) => ruleKey(r) === ruleKey(rule))
            const count = counts.get(ruleKey(rule))
            return (
              <button
                key={ruleKey(rule)}
                onClick={() => toggle(rule)}
                className={cn(
                  'flex items-center gap-2 rounded-[10px] border px-3 py-2 text-xs transition-colors',
                  active
                    ? 'border-accent bg-accent/12 text-accent'
                    : 'border-border text-text-dim hover:border-hairline hover:text-text',
                )}
              >
                <span>{ruleLabel(rule)}</span>
                {count !== undefined && (
                  <span className="tnum font-mono text-[10px] opacity-70">
                    {formatCount(count)}
                  </span>
                )}
              </button>
            )
          })}
        </div>

        <p className="eyebrow mb-2.5 mt-7">Por padrão no conteúdo</p>
        <div className="flex max-w-md gap-2">
          <input
            value={pattern}
            onChange={(e) => setPattern(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addPattern()}
            placeholder="ex.: ^Command: (ls|cat|head)"
            className="flex-1 rounded-[10px] border border-border bg-ink px-3 py-2 font-mono text-xs text-text outline-none transition-colors placeholder:text-text-mute focus:border-accent/60"
          />
          <button onClick={addPattern} className="btn-ghost px-3 text-xs text-text-dim">
            <Plus size={14} />
          </button>
        </div>
        <p className="mt-1.5 font-mono text-[10px] text-text-mute">
          expressão regular, sem diferenciar maiúsculas
        </p>

        {selected.length > 0 && (
          <>
            <p className="eyebrow mb-2.5 mt-7">Regras ativas</p>
            <div className="flex flex-wrap gap-1.5">
              {selected.map((r) => (
                <button
                  key={ruleKey(r)}
                  onClick={() => toggle(r)}
                  className="flex items-center gap-1.5 rounded-[10px] border border-accent bg-accent/12 px-3 py-1.5 text-xs text-accent"
                >
                  {ruleLabel(r)} <X size={12} />
                </button>
              ))}
            </div>
          </>
        )}
      </div>

      <div className="flex min-h-0 flex-col border-l border-border bg-surface">
        <p className="eyebrow border-b border-border px-4 py-3">Prévia</p>

        <div className="flex-1 overflow-y-auto p-4">
          {result ? (
            <p className="text-sm text-teal">{result}</p>
          ) : !preview ? (
            <p className="text-[13px] leading-relaxed text-text-mute">
              {selected.length
                ? 'Rode a prévia para ver exatamente o que será removido.'
                : 'Selecione ao menos uma regra.'}
            </p>
          ) : (
            <>
              <p className="display tnum text-3xl text-text">{formatCount(preview.count)}</p>
              <p className="eyebrow mt-0.5">memórias atingidas</p>
              <p className="mt-2 text-xs text-text-dim">
                {formatSize(preview.size)} de conteúdo
              </p>

              {preview.by_scope.length > 0 && (
                <div className="mt-4 flex flex-col gap-1">
                  {preview.by_scope.map((s) => (
                    <div
                      key={s.scope}
                      className="flex justify-between font-mono text-[11px] text-text-mute"
                    >
                      <span className="truncate">{s.scope}</span>
                      <span className="tnum">{formatCount(s.count)}</span>
                    </div>
                  ))}
                </div>
              )}

              {preview.sample.length > 0 && (
                <>
                  <p className="eyebrow mb-2 mt-5">Amostra</p>
                  <div className="flex flex-col gap-1.5">
                    {preview.sample.map((s) => (
                      <div key={s.id} className="panel p-2.5">
                        <p className="line-clamp-3 text-[11px] leading-snug text-text-dim">
                          {s.content}
                        </p>
                        <p className="mt-1 font-mono text-[9px] text-text-mute">
                          {s._scope} · {formatDateTime(s.created_at)}
                        </p>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </>
          )}
        </div>

        <div className="border-t border-border p-3">
          {confirming && preview ? (
            <div className="flex flex-col gap-2.5">
              <div className="flex items-start gap-2 text-[12px] leading-snug text-text-dim">
                <AlertTriangle size={15} className="mt-px shrink-0 text-magenta" />
                <span>
                  Apagar {formatCount(preview.count)} memórias e os fatos ligados a elas.
                  Não dá pra desfazer.
                </span>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={runDelete}
                  disabled={loading}
                  className="btn-danger flex-1 py-2 text-xs"
                >
                  {loading ? 'Apagando…' : 'Apagar de vez'}
                </button>
                <button
                  onClick={() => setConfirming(false)}
                  className="btn-ghost px-4 py-2 text-xs text-text-dim"
                >
                  Cancelar
                </button>
              </div>
            </div>
          ) : (
            <div className="flex gap-2">
              <button
                onClick={runPreview}
                disabled={!selected.length || loading}
                className="btn-ghost flex-1 py-2 text-xs text-text-dim"
              >
                {loading ? 'Calculando…' : 'Pré-visualizar'}
              </button>
              <button
                onClick={() => setConfirming(true)}
                disabled={!preview || preview.count === 0 || loading}
                className="btn-accent px-4 py-2 text-xs"
              >
                Apagar
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
