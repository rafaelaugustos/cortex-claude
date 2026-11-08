<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { MButton, MEmptyState } from '@getcortexlabs/mavis-web'
import { useMavisTheme } from '@getcortexlabs/mavis-core/vue'
import cytoscape, { type Core } from 'cytoscape'
import type { Graph } from '../lib/api'
const props = defineProps<{ data: Graph }>()
const emit = defineEmits<{ select: [id: string] }>()
const host = ref<HTMLDivElement>()
const { theme } = useMavisTheme()
let cy: Core | undefined
let observer: ResizeObserver | undefined
let alive = true
async function draw() {
  await nextTick()
  if (!alive || !host.value) return
  cy?.destroy(); cy = undefined
  if (!props.data.nodes.length) return
  const colors = theme.value.colors
  const ids = new Map(props.data.nodes.map((node, i) => [node.id, `n${i}`]))
  cy = cytoscape({ container: host.value, elements: [
    ...props.data.nodes.map((node, i) => ({ data: { id: `n${i}`, entity: node.id, label: node.label.length > 28 ? `…${node.label.slice(-27)}` : node.label, weight: node.weight } })),
    ...props.data.edges.flatMap((edge, i) => { const source = ids.get(edge.source), target = ids.get(edge.target); return source && target ? [{ data: { ...edge, id: `e${i}`, source, target } }] : [] }),
  ], style: [
    { selector: 'node', style: { label: 'data(label)', 'background-color': colors.primary, color: colors.muted, 'font-size': 11, 'text-valign': 'bottom', 'text-margin-y': 7, 'text-outline-color': colors.surface, 'text-outline-width': 2, width: 'mapData(weight,1,40,18,50)', height: 'mapData(weight,1,40,18,50)' } },
    { selector: 'edge', style: { width: 1.2, 'line-color': colors.border, 'target-arrow-color': colors.muted, 'target-arrow-shape': 'triangle', 'arrow-scale': .6, 'curve-style': 'bezier' } },
    { selector: '.dim', style: { opacity: .15 } },
    { selector: 'node.focus', style: { 'background-color': colors.accent, color: colors.text, 'border-color': colors.accent, 'border-width': 3 } },
    { selector: 'edge.focus', style: { 'line-color': colors.accent, label: 'data(label)', color: colors.text, 'font-size': 9, 'text-rotation': 'autorotate', 'text-outline-width': 2, 'text-outline-color': colors.surface } },
  ], layout: { name: 'cose', animate: false, padding: 36, nodeRepulsion: () => 5000, idealEdgeLength: () => 75, numIter: 400 }, minZoom: .15, maxZoom: 5, wheelSensitivity: .2 })
  cy.on('tap', 'node', event => { if (!cy) return; cy.elements().removeClass('focus dim').addClass('dim'); event.target.closedNeighborhood().removeClass('dim').addClass('focus'); emit('select', event.target.data('entity')) })
}
function zoom(factor: number) { if (!cy || !host.value) return; cy.zoom({ level: cy.zoom() * factor, renderedPosition: { x: host.value.clientWidth / 2, y: host.value.clientHeight / 2 } }) }
onMounted(() => { void draw(); observer = new ResizeObserver(() => cy?.resize()); if (host.value) observer.observe(host.value) })
watch([() => props.data, theme], draw)
onUnmounted(() => { alive = false; observer?.disconnect(); cy?.destroy() })
</script>
<template>
  <div class="graph-wrap"><div ref="host" class="graph-canvas" aria-hidden="true"></div><MEmptyState v-if="!data.nodes.length" class="graph-empty" compact title="Ainda sem relações" description="As conexões aparecem quando existem fatos ligados a estas memórias." icon="network" /><div v-else class="graph-toolbar row"><MButton icon="maximize-2" variant="secondary" accessibility-label="Ajustar grafo à tela" @click="cy?.fit(undefined, 36)" /><MButton icon="zoom-in" variant="secondary" accessibility-label="Aproximar grafo" @click="zoom(1.3)" /><MButton icon="zoom-out" variant="secondary" accessibility-label="Afastar grafo" @click="zoom(.7)" /><small>{{ data.nodes.length }} entidades · {{ data.edges.length }} relações{{ data.truncated ? ' · exibição parcial' : '' }}</small></div></div>
</template>
