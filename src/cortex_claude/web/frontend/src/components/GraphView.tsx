import { useEffect, useRef, useCallback } from 'react'
import cytoscape, { type Core } from 'cytoscape'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Style = any
import { Maximize2, ZoomIn, ZoomOut, RotateCcw } from 'lucide-react'
import type { GraphData } from '@/lib/api'

interface Props {
  data: GraphData
  onSelectNode: (id: string) => void
  focusNodeId: string | null
}

const NODE_COLORS = [
  '#f97316', '#3b82f6', '#a855f7', '#22c55e', '#ec4899',
  '#14b8a6', '#eab308', '#6366f1', '#f43f5e', '#06b6d4',
]

function hashColor(str: string): string {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash)
  }
  return NODE_COLORS[Math.abs(hash) % NODE_COLORS.length]
}

function darken(hex: string): string {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgb(${Math.floor(r * 0.6)}, ${Math.floor(g * 0.6)}, ${Math.floor(b * 0.6)})`
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
      const color = hashColor(n.id)
      elements.push({
        data: {
          id: n.id,
          label: n.label,
          weight: n.weight,
          color,
          borderColor: darken(color),
        },
      })
    })

    data.edges.forEach((e, i) => {
      elements.push({
        data: {
          id: 'e' + i,
          source: e.source,
          target: e.target,
          label: e.label,
          confidence: e.confidence,
        },
      })
    })

    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: [
        {
          selector: 'node',
          style: {
            'label': 'data(label)',
            'background-color': 'data(color)',
            'border-color': 'data(borderColor)',
            'border-width': 2.5,
            'color': '#c8c8d4',
            'font-size': '11px',
            'font-family': "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
            'font-weight': 500,
            'text-valign': 'bottom',
            'text-halign': 'center',
            'text-margin-y': 8,
            'width': 'mapData(weight, 1, 20, 20, 56)',
            'height': 'mapData(weight, 1, 20, 20, 56)',
            'text-outline-width': 2.5,
            'text-outline-color': '#08080d',
            'text-outline-opacity': 0.9,
            'overlay-opacity': 0,
            'shadow-blur': 12,
            'shadow-color': 'data(color)',
            'shadow-opacity': 0.25,
            'shadow-offset-x': 0,
            'shadow-offset-y': 0,
            'transition-property': 'background-color, border-color, width, height, shadow-opacity, opacity',
            'transition-duration': 300,
          },
        },
        {
          selector: 'edge',
          style: {
            'width': 'mapData(confidence, 0.5, 1, 0.8, 2)',
            'line-color': '#252538',
            'line-opacity': 0.6,
            'target-arrow-color': '#252538',
            'target-arrow-shape': 'triangle',
            'arrow-scale': 0.6,
            'curve-style': 'bezier',
            'control-point-step-size': 40,
            'label': 'data(label)',
            'font-size': '8px',
            'font-family': "'SF Mono', 'Fira Code', monospace",
            'font-weight': 400,
            'color': '#3a3a50',
            'text-rotation': 'autorotate',
            'text-outline-width': 2,
            'text-outline-color': '#08080d',
            'text-outline-opacity': 0.8,
            'text-margin-y': -8,
            'overlay-opacity': 0,
            'transition-property': 'line-color, target-arrow-color, width, opacity, line-opacity',
            'transition-duration': 300,
          },
        },
        {
          selector: 'node.selected-node',
          style: {
            'border-width': 4,
            'border-color': '#ffffff',
            'shadow-opacity': 0.6,
            'shadow-blur': 24,
            'font-size': '13px',
            'font-weight': 700,
            'color': '#ffffff',
            'z-index': 999,
          },
        },
        {
          selector: 'node.neighbor',
          style: {
            'shadow-opacity': 0.4,
            'shadow-blur': 16,
            'border-width': 3,
            'color': '#e0e0e8',
          },
        },
        {
          selector: 'edge.highlighted',
          style: {
            'line-color': '#f97316',
            'target-arrow-color': '#f97316',
            'line-opacity': 1,
            'width': 2.5,
            'color': '#f97316',
            'font-size': '9px',
            'z-index': 998,
          },
        },
        {
          selector: 'node.faded',
          style: {
            'opacity': 0.1,
          },
        },
        {
          selector: 'edge.faded',
          style: {
            'opacity': 0.04,
          },
        },
      ],
      layout: {
        name: 'cose',
        animate: true,
        animationDuration: 1000,
        animationEasing: 'ease-out-cubic' as any,
        nodeRepulsion: () => 12000,
        idealEdgeLength: () => 140,
        edgeElasticity: () => 100,
        gravity: 0.25,
        numIter: 1000,
        padding: 80,
        nodeDimensionsIncludeLabels: true,
      },
      minZoom: 0.1,
      maxZoom: 6,
      wheelSensitivity: 0.3,
      pixelRatio: 2,
    })

    cy.on('tap', 'node', evt => {
      const node = evt.target
      highlightNode(cy, node.id())
      onSelectNode(node.id())
    })

    cy.on('tap', evt => {
      if (evt.target === cy) {
        clearHighlight(cy)
        onSelectNode('')
      }
    })

    cy.on('mouseover', 'node', () => {
      containerRef.current!.style.cursor = 'pointer'
    })

    cy.on('mouseout', 'node', () => {
      containerRef.current!.style.cursor = 'default'
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
        cy.animate({ center: { eles: node }, zoom: 2.5 }, { duration: 500, easing: 'ease-out-cubic' as any })
        highlightNode(cy, focusNodeId)
      }
    }
  }, [focusNodeId])

  return (
    <div className="relative w-full h-full">
      {/* Subtle grid background */}
      <div
        className="absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage: 'radial-gradient(circle, #ffffff 1px, transparent 1px)',
          backgroundSize: '24px 24px',
        }}
      />

      <div ref={containerRef} className="w-full h-full relative z-10" />

      {data.nodes.length === 0 && (
        <div className="absolute inset-0 flex flex-col items-center justify-center text-text-dim z-20">
          <div className="w-16 h-16 rounded-full bg-card border border-border flex items-center justify-center mb-4">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="12" cy="12" r="3" />
              <circle cx="5" cy="6" r="2" />
              <circle cx="19" cy="6" r="2" />
              <circle cx="5" cy="18" r="2" />
              <circle cx="19" cy="18" r="2" />
              <line x1="9.5" y1="10.5" x2="6.5" y2="7.5" />
              <line x1="14.5" y1="10.5" x2="17.5" y2="7.5" />
              <line x1="9.5" y1="13.5" x2="6.5" y2="16.5" />
              <line x1="14.5" y1="13.5" x2="17.5" y2="16.5" />
            </svg>
          </div>
          <p className="text-sm">No graph data yet</p>
          <p className="text-xs mt-1">Save some memories to see the knowledge graph</p>
        </div>
      )}

      {/* Controls */}
      <div className="absolute bottom-4 left-4 flex gap-1 z-20">
        <GraphBtn
          icon={<Maximize2 size={14} />}
          tooltip="Fit to view"
          onClick={() => cyRef.current?.fit(undefined, 60)}
        />
        <GraphBtn
          icon={<ZoomIn size={14} />}
          tooltip="Zoom in"
          onClick={() => {
            const cy = cyRef.current
            if (cy) cy.animate({ zoom: { level: cy.zoom() * 1.5, position: cy.extent() as any } }, { duration: 200 })
          }}
        />
        <GraphBtn
          icon={<ZoomOut size={14} />}
          tooltip="Zoom out"
          onClick={() => {
            const cy = cyRef.current
            if (cy) cy.animate({ zoom: { level: cy.zoom() * 0.67, position: cy.extent() as any } }, { duration: 200 })
          }}
        />
        <GraphBtn
          icon={<RotateCcw size={14} />}
          tooltip="Re-layout"
          onClick={() => {
            if (!cyRef.current) return
            clearHighlight(cyRef.current)
            cyRef.current.layout({
              name: 'cose',
              animate: true,
              animationDuration: 800,
              nodeRepulsion: () => 12000,
              idealEdgeLength: () => 140,
              gravity: 0.25,
              padding: 80,
              nodeDimensionsIncludeLabels: true,
            }).run()
          }}
        />
      </div>

      {/* Node count badge */}
      {data.nodes.length > 0 && (
        <div className="absolute bottom-4 right-4 z-20 bg-card/80 backdrop-blur border border-border rounded-lg px-3 py-1.5 text-xs text-text-dim font-mono">
          {data.nodes.length} nodes &middot; {data.edges.length} edges
        </div>
      )}
    </div>
  )
}

function GraphBtn({ icon, tooltip, onClick }: { icon: React.ReactNode; tooltip: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      title={tooltip}
      className="bg-card/80 backdrop-blur border border-border rounded-lg p-2 text-text-dim hover:text-text hover:bg-card-hover hover:border-accent/40 transition-all duration-200"
    >
      {icon}
    </button>
  )
}

function highlightNode(cy: Core, nodeId: string) {
  clearHighlight(cy)
  const node = cy.getElementById(nodeId)
  if (!node.length) return

  cy.elements().addClass('faded')
  node.removeClass('faded').addClass('selected-node')
  node.connectedEdges().removeClass('faded').addClass('highlighted')
  node.neighborhood('node').removeClass('faded').addClass('neighbor')
}

function clearHighlight(cy: Core) {
  cy.elements().removeClass('selected-node neighbor highlighted faded')
}
