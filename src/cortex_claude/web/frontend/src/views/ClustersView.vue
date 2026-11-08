<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { MAlert, MBadge, MButton, MCard, MEmptyState, MInput, MPagination, MSelect, MSheet } from '@getcortexlabs/mavis-web'
import type { ChoiceValue } from '@getcortexlabs/mavis-core'
import { fetchCluster, fetchClusters, fetchEntity, type Cluster, type ClusterDetail, type Fact, type Memory, type Overview } from '../lib/api'
import GraphView from '../components/GraphView.vue'
import MemoryDetail from '../components/MemoryDetail.vue'
const props = defineProps<{ overview: Overview }>()
const query = ref('')
const scope = ref<ChoiceValue | null>('')
const sort = ref<ChoiceValue | null>('size')
const scopes = computed(() => [{ value: '', label: 'Todos os projetos' }, ...props.overview.scopes.map(s => ({ value: s.name, label: s.name }))])
const items = ref<Cluster[]>([])
const total = ref(0)
const page = ref(1)
const detail = ref<ClusterDetail>()
const entityName = ref<ChoiceValue | null>(null)
const entity = ref<{ facts: Fact[]; memories: Memory[] }>()
const memoryId = ref<string | null>(null)
const error = ref('')
const loading = ref(true)
const open = ref(false)
let generation = 0, detailGeneration = 0, entityGeneration = 0
let debounce: ReturnType<typeof setTimeout>
async function load() { const request = ++generation; loading.value = true; try { const data = await fetchClusters({ q: query.value, scope: String(scope.value || ''), sort: String(sort.value), limit: 18, offset: (page.value - 1) * 18 }); if (generation === request) { items.value = data.items; total.value = data.total; error.value = '' } } catch (e) { if (generation === request) error.value = String(e) } finally { if (generation === request) loading.value = false } }
async function inspect(item: Cluster) { const request = ++detailGeneration; detail.value = undefined; entity.value = undefined; entityName.value = null; open.value = true; error.value = ''; try { const value = await fetchCluster(item.id, item.scope); if (request === detailGeneration) detail.value = value } catch (e) { if (request === detailGeneration) error.value = String(e) } }
watch([scope, sort], () => { if (page.value !== 1) page.value = 1; else void load() })
watch(query, () => { generation++; clearTimeout(debounce); debounce = setTimeout(() => { if (page.value !== 1) page.value = 1; else void load() }, 220) })
watch(page, load, { immediate: true })
watch(entityName, async name => { const request = ++entityGeneration; entity.value = undefined; if (!name) return; try { const value = await fetchEntity(String(name)); if (request === entityGeneration) entity.value = value } catch (e) { if (request === entityGeneration) error.value = String(e) } })
onUnmounted(() => { generation++; detailGeneration++; entityGeneration++; clearTimeout(debounce) })
</script>
<template>
  <div class="stack"><div class="filters"><MInput v-model="query" label="Buscar assuntos" placeholder="Nome do grupo…" icon="search" type="search" /><MSelect v-model="scope" :options="scopes" label="Projeto" close-label="Fechar opções" /><MSelect v-model="sort" :options="[{ value: 'size', label: 'Mais memórias' }, { value: 'recent', label: 'Atualizados recentemente' }]" label="Ordenar" close-label="Fechar opções" /></div><MAlert v-if="error && !open" title="Não foi possível carregar as conexões" :description="error" tone="error"><template #actions><MButton @click="load">Tentar novamente</MButton></template></MAlert><p v-if="loading" role="status">Carregando assuntos…</p><MEmptyState v-else-if="!items.length" title="Nenhum assunto encontrado" description="As memórias relacionadas são agrupadas conforme o arquivo cresce." icon="network" /><div class="cluster-grid"><MCard v-for="item in items" :key="`${item.scope}:${item.id}`" gap="lg" interactive :accessibility-label="`Explorar ${item.label || 'grupo sem título'}`" @click="inspect(item)"><MBadge :text="`${item.member_count} memórias`" tone="accent" /><h2>{{ item.label || 'Grupo sem título' }}</h2><small class="path">{{ item.scope }}</small></MCard></div><MPagination v-if="total > 18" v-model="page" :total="total" :page-size="18" :loading="loading" label="Páginas de assuntos" previous-label="Anterior" next-label="Próxima" /><MSheet v-model:open="open" :title="detail?.cluster.label || 'Explorar conexões'" close-label="Fechar conexões"><div class="sheet-content wide stack"><MAlert v-if="error" title="Não foi possível carregar" :description="error" tone="error" /><p v-if="!detail && !error" role="status">Carregando relações…</p><template v-if="detail"><GraphView :data="detail.graph" @select="value => entityName = value" /><MSelect v-model="entityName" label="Explorar uma entidade" :options="detail.graph.nodes.map(node => ({ value: node.id, label: node.label }))" placeholder="Escolha no grafo ou nesta lista" close-label="Fechar entidades" /><div v-if="entity"><h3>Relações de {{ entityName }}</h3><ul class="evidence-list"><li v-for="(fact, i) in entity.facts" :key="i">{{ fact.subject }} → {{ fact.relation }} → {{ fact.object }}</li></ul></div><h3>Memórias relacionadas</h3><MCard v-for="memory in entity?.memories || detail.memories" :key="memory.id" interactive class="memory-preview" :accessibility-label="`Abrir memória ${memory.id}`" @click="memoryId = memory.id"><p>{{ (memory.summary || memory.content).slice(0, 240) }}</p></MCard></template></div></MSheet><MemoryDetail :id="memoryId" @close="memoryId = null" @changed="open = false; load()" /></div>
</template>
