import { useEffect, useRef, useCallback } from 'react'
import cytoscape, { type Core } from 'cytoscape'
import { Maximize2, ZoomIn, ZoomOut, RotateCcw } from 'lucide-react'
import type { GraphData } from '@/lib/api'

interface Props {
  data: GraphData
  onSelectNode: (id: string) => void
  focusNodeId: string | null
}

export function GraphView({ data, onSelectNode, focusNodeId }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const cyRef = useRef<Core | null>(null)

  const initGraph = useCallback(() => {
    if (!containerRef.current || !data.nodes.length) return

    if (cyRef.current) {
      cyRef.current.destroy()
    }

    const elements: cytoscape.ElementDefinition[] = []

    data.nodes.forEach(n => {
      elements.push({ data: { id: n.id, label: n.label, weight: n.weight } })
    })

    data.edges.forEach((e, i) => {
      elements.push({ data: { id: 'e' + i, source: e.source, target: e.target, label: e.label, confidence: e.confidence } })
    })

    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: [
        {
          selector: 'node',
          style: {
            'label': 'data(label)',
            'background-color': '#f97316',
            'color': '#e0e0e8',
            'font-size': '10px',
            'font-family': "'SF Mono', 'Fira Code', monospace",
            'text-valign': 'bottom',
            'text-margin-y': 6,
            'width': 'mapData(weight, 1, 20, 14, 44)',
            'height': 'mapData(weight, 1, 20, 14, 44)',
            'border-width': 2,
            'border-color': '#c2410c',
            'text-outline-width': 2,
            'text-outline-color': '#0a0a0f',
            'transition-property': 'background-color, border-color, width, height',
            'transition-duration': 200,
          },
        },
        {
          selector: 'edge',
          style: {
            'label': 'data(label)',
            'width': 'mapData(confidence, 0.5, 1, 1, 2.5)',
            'line-color': '#1e1e30',
            'target-arrow-color': '#1e1e30',
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier',
            'font-size': '8px',
            'font-family': "'SF Mono', monospace",
            'color': '#4a4a60',
            'text-rotation': 'autorotate',
            'text-outline-width': 2,
            'text-outline-color': '#0a0a0f',
            'arrow-scale': 0.7,
            'transition-property': 'line-color, target-arrow-color, width',
            'transition-duration': 200,
          },
        },
        {
          selector: 'node.highlight',
          style: {
            'background-color': '#3b82f6',
            'border-color': '#2563eb',
            'font-size': '12px',
            'text-outline-width': 3,
          },
        },
        {
          selector: 'node.neighbor',
          style: {
            'background-color': '#22c55e',
            'border-color': '#16a34a',
          },
        },
        {
          selector: 'edge.highlight',
          style: {
            'line-color': '#f97316',
            'target-arrow-color': '#f97316',
            'width': 3,
            'color': '#f97316',
          },
        },
        {
          selector: 'node.dimmed',
          style: {
            'opacity': 0.15,
          },
        },
        {
          selector: 'edge.dimmed',
          style: {
            'opacity': 0.08,
          },
        },
      ],
      layout: {
        name: 'cose',
        animate: true,
        animationDuration: 800,
        nodeRepulsion: () => 8000,
        idealEdgeLength: () => 120,
        gravity: 0.3,
        padding: 60,
      },
      minZoom: 0.15,
      maxZoom: 5,
    })

    cy.on('tap', 'node', evt => {
      const node = evt.target
      highlightNode(cy, node.id())
      onSelectNode(node.id())
    })

    cy.on('tap', evt => {
      if (evt.target === cy) {
        cy.elements().removeClass('highlight neighbor dimmed')
        onSelectNode('')
      }
    })

    cyRef.current = cy
  }, [data, onSelectNode])

  useEffect(() => {
    initGraph()
    return () => { cyRef.current?.destroy() }
  }, [initGraph])

  useEffect(() => {
    if (focusNodeId && cyRef.current) {
      const cy = cyRef.current
      const node = cy.getElementById(focusNodeId)
      if (node.length) {
        cy.animate({ center: { eles: node }, zoom: 2.5 }, { duration: 400 })
        highlightNode(cy, focusNodeId)
      }
    }
  }, [focusNodeId])

  return (
    <div className="relative w-full h-full">
      <div ref={containerRef} className="w-full h-full" />

      {data.nodes.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center text-text-dim text-sm">
          No graph data yet. Save some memories to see the knowledge graph.
        </div>
      )}

      <div className="absolute bottom-4 left-4 flex gap-1.5">
        <GraphBtn icon={<Maximize2 size={14} />} onClick={() => cyRef.current?.fit(undefined, 50)} />
        <GraphBtn icon={<ZoomIn size={14} />} onClick={() => cyRef.current?.zoom((cyRef.current?.zoom() ?? 1) * 1.4)} />
        <GraphBtn icon={<ZoomOut size={14} />} onClick={() => cyRef.current?.zoom((cyRef.current?.zoom() ?? 1) * 0.7)} />
        <GraphBtn icon={<RotateCcw size={14} />} onClick={() => {
          cyRef.current?.layout({
            name: 'cose', animate: true, animationDuration: 600,
            nodeRepulsion: () => 8000, idealEdgeLength: () => 120, gravity: 0.3, padding: 60,
          }).run()
        }} />
      </div>
    </div>
  )
}

function GraphBtn({ icon, onClick }: { icon: React.ReactNode; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="bg-card border border-border rounded-lg p-2 text-text hover:bg-card-hover hover:border-accent/50 transition-colors"
    >
      {icon}
    </button>
  )
}

function highlightNode(cy: Core, nodeId: string) {
  cy.elements().removeClass('highlight neighbor dimmed')
  const node = cy.getElementById(nodeId)
  if (!node.length) return

  cy.elements().addClass('dimmed')
  node.removeClass('dimmed').addClass('highlight')
  node.connectedEdges().removeClass('dimmed').addClass('highlight')
  node.neighborhood('node').removeClass('dimmed').addClass('neighbor')
}
