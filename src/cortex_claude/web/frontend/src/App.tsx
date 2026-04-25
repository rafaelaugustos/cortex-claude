import { useEffect, useState, useCallback, useMemo } from 'react'
import { Header } from '@/components/Header'
import { Sidebar } from '@/components/Sidebar'
import { GraphView } from '@/components/GraphView'
import { EntityDetail, MemoryDetail } from '@/components/DetailPanel'
import { fetchStats, fetchMemories, fetchGraph, fetchEntity, searchMemories } from '@/lib/api'
import type { Stats, Memory, GraphData, EntityData } from '@/lib/api'

export default function App() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [memories, setMemories] = useState<Memory[]>([])
  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], edges: [] })
  const [focusNodeId, setFocusNodeId] = useState<string | null>(null)

  const [selectedEntity, setSelectedEntity] = useState<{ name: string; data: EntityData } | null>(null)
  const [selectedMemory, setSelectedMemory] = useState<Memory | null>(null)

  const scopes = useMemo(() => {
    if (!stats) return []
    return stats.scopes.map(s => s.name)
  }, [stats])

  useEffect(() => {
    fetchStats().then(setStats)
    fetchMemories().then(setMemories)
    fetchGraph().then(setGraphData)
  }, [])

  const handleSearch = useCallback(async (q: string) => {
    if (q.length < 2) {
      fetchMemories().then(setMemories)
      return
    }
    const results = await searchMemories(q)
    setMemories(results)
  }, [])

  const handleSelectNode = useCallback(async (id: string) => {
    if (!id) {
      setSelectedEntity(null)
      return
    }
    const data = await fetchEntity(id)
    setSelectedEntity({ name: id, data })
    setSelectedMemory(null)
  }, [])

  const handleSelectMemory = useCallback((id: string) => {
    const mem = memories.find(m => m.id === id)
    if (mem) {
      setSelectedMemory(mem)
      setSelectedEntity(null)
    }
  }, [memories])

  const handleFocusNode = useCallback((id: string) => {
    setFocusNodeId(id)
    setTimeout(() => setFocusNodeId(null), 500)
  }, [])

  return (
    <div className="grid grid-cols-[320px_1fr] grid-rows-[56px_1fr] h-screen">
      <div className="col-span-2">
        <Header stats={stats} />
      </div>

      <Sidebar
        memories={memories}
        facts={graphData.edges}
        scopes={scopes}
        onSearch={handleSearch}
        onSelectMemory={handleSelectMemory}
        onFocusNode={handleFocusNode}
      />

      <main className="relative bg-bg overflow-hidden">
        <GraphView
          data={graphData}
          onSelectNode={handleSelectNode}
          focusNodeId={focusNodeId}
        />

        {selectedEntity && (
          <EntityDetail
            name={selectedEntity.name}
            data={selectedEntity.data}
            onClose={() => setSelectedEntity(null)}
          />
        )}

        {selectedMemory && (
          <MemoryDetail
            memory={selectedMemory}
            onClose={() => setSelectedMemory(null)}
          />
        )}
      </main>
    </div>
  )
}
