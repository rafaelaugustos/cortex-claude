import { useCallback, useEffect, useState } from 'react'
import { Header } from '@/components/Header'
import { Sidebar, type View } from '@/components/Sidebar'
import { ClusterGrid } from '@/components/ClusterGrid'
import { ClusterDetail } from '@/components/ClusterDetail'
import { MemoryList } from '@/components/MemoryList'
import { Cleanup } from '@/components/Cleanup'
import { EntityPanel, MemoryPanel } from '@/components/DetailPanel'
import { fetchOverview, type CleanupRule, type Cluster, type Memory, type Overview } from '@/lib/api'

export default function App() {
  const [overview, setOverview] = useState<Overview | null>(null)
  const [view, setView] = useState<View>('clusters')
  const [scope, setScope] = useState('all')
  const [tag, setTag] = useState<string | null>(null)
  const [cluster, setCluster] = useState<Cluster | null>(null)
  const [memory, setMemory] = useState<Memory | null>(null)
  const [entity, setEntity] = useState<string | null>(null)
  const [seedRules, setSeedRules] = useState<CleanupRule[]>([])
  const [refreshKey, setRefreshKey] = useState(0)

  const reload = useCallback(() => {
    fetchOverview().then(setOverview).catch(() => setOverview(null))
    setRefreshKey((k) => k + 1)
  }, [])

  useEffect(() => {
    fetchOverview().then(setOverview).catch(() => setOverview(null))
  }, [])

  const goView = (v: View) => {
    setView(v)
    setCluster(null)
    setMemory(null)
    setEntity(null)
  }

  const pickTag = (t: string | null) => {
    setTag(t)
    if (t) {
      setView('memories')
      setCluster(null)
    }
  }

  const openMemory = (m: Memory) => {
    setMemory(m)
    setEntity(null)
  }

  const openEntity = (name: string) => {
    setEntity(name)
    setMemory(null)
  }

  const cleanCluster = (c: Cluster) => {
    setSeedRules([{ type: 'cluster', value: c.id, scope: c.scope }])
    goView('cleanup')
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-ink">
      <Header overview={overview} />

      <div className="flex min-h-0 flex-1">
        <Sidebar
          overview={overview}
          view={view}
          scope={scope}
          tag={tag}
          onView={goView}
          onScope={(s) => {
            setScope(s)
            setCluster(null)
          }}
          onTag={pickTag}
        />

        <main className="relative min-w-0 flex-1 overflow-hidden">
          {view === 'clusters' &&
            (cluster ? (
              <ClusterDetail
                cluster={cluster}
                onBack={() => setCluster(null)}
                onSelectMemory={openMemory}
                onSelectEntity={openEntity}
                onCleanCluster={cleanCluster}
              />
            ) : (
              <ClusterGrid scope={scope} onOpen={setCluster} />
            ))}

          {view === 'memories' && (
            <MemoryList
              scope={scope}
              tag={tag}
              onClearTag={() => setTag(null)}
              onSelect={openMemory}
              selectedId={memory?.id}
              refreshKey={refreshKey}
            />
          )}

          {view === 'cleanup' && (
            <Cleanup
              overview={overview}
              seedRules={seedRules}
              onSeedConsumed={() => setSeedRules([])}
              onDone={reload}
            />
          )}

          {memory && (
            <MemoryPanel
              memory={memory}
              onClose={() => setMemory(null)}
              onChanged={reload}
            />
          )}

          {entity && (
            <EntityPanel
              name={entity}
              onClose={() => setEntity(null)}
              onSelectMemory={openMemory}
              onSelectEntity={setEntity}
            />
          )}
        </main>
      </div>
    </div>
  )
}
