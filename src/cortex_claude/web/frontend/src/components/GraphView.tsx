import { useCallback, useEffect, useRef } from 'react'
import cytoscape, { type Core } from 'cytoscape'
import { Maximize2, RotateCcw, ZoomIn, ZoomOut } from 'lucide-react'
import type { Graph } from '@/lib/api'

interface Props {
  data: Graph
  onSelectNode: (id: string) => void
  emptyLabel?: string
}

/* The family palette. Nodes borrow the sibling products' signatures so the
   graph reads as Cortex Labs, not as a rainbow. */
const PALETTE = ['#ff8a5c', '#7b61ff', '#3aa0ec', '#4fd6c0', '#ff5aa0', '#f2c14e']

function hashColor(s: string): string {
  let h = 0
  for (let i = 0; i < s.length; i++) h = s.charCodeAt(i) + ((h << 5) - h)
  return PALETTE[Math.abs(h) % PALETTE.length]
}

/* Long entity keys (file paths, mostly) blow the layout out. Show the tail. */
function trim(label: string): string {
  const s = label.trim()
  if (s.length <= 26) return s
  return '…' + s.slice(-25)
}

const LAYOUT = {
  name: 'cose',
  animate: false,
  nodeRepulsion: () => 4200,
  idealEdgeLength: () => 55,
  edgeElasticity: () => 120,
  gravity: 0.9,
  numIter: 500,
  padding: 40,
  nodeDimensionsIncludeLabels: false,
  randomize: true,
} as const

/* Below this zoom the labels are unreadable anyway and just make a smear. */
const LABEL_ZOOM = 0.62

export function GraphView({ data, onSelectNode, emptyLabel }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const cyRef = useRef<Core | null>(null)

  const build = useCallback(() => {
    const container = containerRef.current
    if (!container) return

    cyRef.current?.destroy()
    cyRef.current = null
    if (!data.nodes.length) return

    /* Entity names go in as `data.entity`, never as the element id.
       Cytoscape keys its internal traversal state on a bare object, so an
       entity literally called "constructor" or "toString" resolves to an
       inherited function and the layout throws. Synthetic ids are immune. */
    const idOf = new Map<string, string>()
    data.nodes.forEach((n, i) => idOf.set(n.id, `n${i}`))

    const elements: cytoscape.ElementDefinition[] = [
      ...data.nodes.map((n, i) => ({
        data: {
          id: `n${i}`,
          entity: n.id,
          label: trim(n.label),
          weight: n.weight,
          color: hashColor(n.id),
        },
      })),
      ...data.edges.flatMap((e, i) => {
        const source = idOf.get(e.source)
        const target = idOf.get(e.target)
        if (!source || !target) return []
        return [{
          data: { id: `e${i}`, source, target, label: e.label, confidence: e.confidence },
        }]
      }),
    ]

    const cy = cytoscape({
      container,
      elements,
      style: [
        {
          selector: 'node',
          style: {
            label: 'data(label)',
            'background-color': 'data(color)',
            'background-opacity': 0.9,
            'border-width': 1.5,
            'border-color': '#08080b',
            color: '#8d8d9e',
            'font-size': '10px',
            'font-family': 'ui-sans-serif, system-ui, sans-serif',
            'font-weight': 500,
            'text-valign': 'bottom',
            'text-halign': 'center',
            'text-margin-y': 6,
            'text-outline-width': 3,
            'text-outline-color': '#08080b',
            width: 'mapData(weight, 1, 40, 14, 46)',
            height: 'mapData(weight, 1, 40, 14, 46)',
            'overlay-opacity': 0,
            'transition-property': 'opacity, border-width, border-color, color',
            'transition-duration': 180,
          },
        },
        {
          selector: 'edge',
          style: {
            width: 'mapData(confidence, 0.4, 1, 0.5, 1.6)',
            'line-color': '#21212e',
            'target-arrow-color': '#21212e',
            'target-arrow-shape': 'triangle',
            'arrow-scale': 0.55,
            'curve-style': 'bezier',
            'overlay-opacity': 0,
            'transition-property': 'opacity, line-color, target-arrow-color, width',
            'transition-duration': 180,
          },
        },
        {
          selector: 'node.selected',
          style: {
            'border-width': 3,
            'border-color': '#ff8a5c',
            color: '#ececf2',
            'font-size': '12px',
            'font-weight': 700,
            'z-index': 999,
          },
        },
        {
          selector: 'node.neighbor',
          style: { color: '#ececf2', 'border-color': '#2b2b3a', 'border-width': 2 },
        },
        {
          selector: 'edge.active',
          style: {
            'line-color': '#ff8a5c',
            'target-arrow-color': '#ff8a5c',
            width: 1.8,
            label: 'data(label)',
            'font-size': '9px',
            'font-family': "'SF Mono', ui-monospace, monospace",
            color: '#ff8a5c',
            'text-rotation': 'autorotate',
            'text-outline-width': 3,
            'text-outline-color': '#08080b',
            'z-index': 998,
          },
        },
        { selector: 'node.quiet', style: { 'text-opacity': 0 } },
        { selector: '.dim', style: { opacity: 0.12 } },
      ],
      layout: LAYOUT,
      minZoom: 0.15,
      maxZoom: 5,
      wheelSensitivity: 0.25,
      textureOnViewport: data.nodes.length > 120,
      motionBlur: false,
      pixelRatio: 1,
    })

    cy.on('tap', 'node', (evt) => {
      focus(cy, evt.target.id())
      onSelectNode(evt.target.data('entity'))
    })

    cy.on('tap', (evt) => {
      if (evt.target === cy) {
        clear(cy)
        onSelectNode('')
      }
    })

    cy.on('mouseover', 'node', () => {
      container.style.cursor = 'pointer'
    })
    cy.on('mouseout', 'node', () => {
      container.style.cursor = 'grab'
    })

    let quiet: boolean | null = null
    const syncLabels = () => {
      const next = cy.zoom() < LABEL_ZOOM
      if (next === quiet) return
      quiet = next
      cy.batch(() => cy.nodes().toggleClass('quiet', next))
    }
    cy.on('zoom', syncLabels)

    cy.ready(() => {
      cy.fit(undefined, 40)
      syncLabels()
    })
    cyRef.current = cy
  }, [data, onSelectNode])

  useEffect(() => {
    build()
    return () => {
      cyRef.current?.destroy()
      cyRef.current = null
    }
  }, [build])

  return (
    <div className="relative h-full w-full">
      <div className="grid-field" />
      <div ref={containerRef} className="relative z-10 h-full w-full" />

      {!data.nodes.length && (
        <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-2 text-text-mute">
          <div className="panel flex h-14 w-14 items-center justify-center">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
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
          <p className="text-sm">{emptyLabel ?? 'Sem fatos para desenhar aqui.'}</p>
        </div>
      )}

      {data.nodes.length > 0 && (
        <>
          <div className="absolute bottom-4 left-4 z-20 flex gap-1.5">
            <GraphBtn title="Ajustar à tela" onClick={() => cyRef.current?.fit(undefined, 50)}>
              <Maximize2 size={13} />
            </GraphBtn>
            <GraphBtn
              title="Aproximar"
              onClick={() => cyRef.current?.zoom({ level: (cyRef.current?.zoom() ?? 1) * 1.4, renderedPosition: center(cyRef.current) })}
            >
              <ZoomIn size={13} />
            </GraphBtn>
            <GraphBtn
              title="Afastar"
              onClick={() => cyRef.current?.zoom({ level: (cyRef.current?.zoom() ?? 1) * 0.7, renderedPosition: center(cyRef.current) })}
            >
              <ZoomOut size={13} />
            </GraphBtn>
            <GraphBtn
              title="Recalcular layout"
              onClick={() => {
                const cy = cyRef.current
                if (!cy) return
                clear(cy)
                cy.layout(LAYOUT).run()
                cy.fit(undefined, 50)
              }}
            >
              <RotateCcw size={13} />
            </GraphBtn>
          </div>

          <div className="panel absolute bottom-4 right-4 z-20 px-3 py-1.5 font-mono text-[11px] text-text-mute tnum">
            {data.nodes.length} nós · {data.edges.length} arestas
            {data.truncated && (
              <span className="ml-1.5 text-accent" title={`sub-grafo completo: ${data.total_nodes} nós, ${data.total_edges} arestas`}>
                (top de {data.total_edges.toLocaleString('pt-BR')})
              </span>
            )}
          </div>
        </>
      )}
    </div>
  )
}

function center(cy: Core | null): { x: number; y: number } {
  const c = cy?.container()
  return c ? { x: c.clientWidth / 2, y: c.clientHeight / 2 } : { x: 0, y: 0 }
}

function GraphBtn({ title, onClick, children }: { title: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      title={title}
      className="panel panel-link p-2 text-text-mute hover:text-text"
    >
      {children}
    </button>
  )
}

function focus(cy: Core, id: string) {
  clear(cy)
  const node = cy.getElementById(id)
  if (!node.length) return
  cy.elements().addClass('dim')
  node.removeClass('dim').addClass('selected')
  node.connectedEdges().removeClass('dim').addClass('active')
  node.neighborhood('node').removeClass('dim').addClass('neighbor')
}

function clear(cy: Core) {
  cy.elements().removeClass('dim selected neighbor active')
}
