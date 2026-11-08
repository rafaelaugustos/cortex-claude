<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { MAlert, MBadge, MButton, MCard, MDataTable, MEmptyState, MInput, MPagination, MSelect } from '@getcortexlabs/mavis-web'
import type { ChoiceValue } from '@getcortexlabs/mavis-core'
import { fetchMemories, formatDate, parseTags, type Memory, type Overview } from '../lib/api'
import MemoryDetail from '../components/MemoryDetail.vue'
const props = defineProps<{ overview: Overview }>()
const emit = defineEmits<{ refresh: [] }>()
const items = ref<Memory[]>([])
const total = ref(0)
const query = ref('')
const scope = ref<ChoiceValue | null>('')
const tag = ref<ChoiceValue | null>('')
const sort = ref<ChoiceValue | null>('recent')
const page = ref(1)
const selected = ref<string | null>(null)
const error = ref('')
const loading = ref(true)
const scopes = computed(() => [{ value: '', label: 'Todos os projetos' }, ...props.overview.scopes.map(s => ({ value: s.name, label: s.name }))])
const tags = computed(() => [{ value: '', label: 'Todas as tags' }, ...props.overview.tags.map(t => ({ value: t.name, label: `${t.name} (${t.count})` }))])
const columns = [{ key: 'content', label: 'Memória' }, { key: '_scope', label: 'Projeto' }, { key: 'tags', label: 'Tags' }, { key: 'created_at', label: 'Criada em' }]
let generation = 0
let debounce: ReturnType<typeof setTimeout>
async function load() { const request = ++generation; loading.value = true; error.value = ''; try { const result = await fetchMemories({ q: query.value, scope: String(scope.value || ''), tag: String(tag.value || ''), sort: String(sort.value), limit: 20, offset: (page.value - 1) * 20 }); if (generation !== request) return; items.value = result.items; total.value = result.total; if (page.value > Math.max(1, Math.ceil(result.total / 20))) page.value = Math.max(1, Math.ceil(result.total / 20)) } catch (e) { if (generation === request) error.value = String(e) } finally { if (generation === request) loading.value = false } }
watch([scope, tag, sort], () => { if (page.value !== 1) page.value = 1; else void load() })
watch(query, () => { generation++; clearTimeout(debounce); debounce = setTimeout(() => { if (page.value !== 1) page.value = 1; else void load() }, 220) })
watch(page, load, { immediate: true })
onUnmounted(() => { generation++; clearTimeout(debounce) })
function changed() { void load(); emit('refresh') }
</script>
<template>
  <div class="stack"><div class="filters archive-filters"><MInput v-model="query" label="Buscar no arquivo" placeholder="Conteúdo da memória…" icon="search" type="search" /><MSelect v-model="scope" :options="scopes" label="Projeto" close-label="Fechar opções" /><MSelect v-model="tag" :options="tags" label="Tag" close-label="Fechar opções" /><MSelect v-model="sort" :options="[{ value: 'recent', label: 'Mais recentes' }, { value: 'oldest', label: 'Mais antigas' }, { value: 'accessed', label: 'Acessadas recentemente' }, { value: 'largest', label: 'Maior conteúdo' }]" label="Ordenar" close-label="Fechar opções" /></div><MAlert v-if="error" title="Não foi possível carregar o arquivo" :description="error" tone="error"><template #actions><MButton @click="load">Tentar novamente</MButton></template></MAlert><MCard padding="none" class="table-card"><MDataTable :items="items" :columns="columns" :loading="loading" label="Memórias arquivadas"><template #cell:content="{ item }"><MButton variant="ghost" class="table-content" @click="selected = String(item.id)">{{ String(item.summary || item.content).slice(0, 180) }}</MButton></template><template #cell:tags="{ item }"><div class="row wrap"><MBadge v-for="value in parseTags(String(item.tags))" :key="value" :text="value" size="sm" /></div></template><template #cell:created_at="{ item }">{{ formatDate(Number(item.created_at)) }}</template><template #empty><MEmptyState compact title="Nenhuma memória encontrada" description="Tente outros filtros ou salve conteúdo durante uma conversa." icon="archive" /></template></MDataTable><div class="table-footer"><small>{{ total }} memórias</small><MPagination v-model="page" :total="total" :page-size="20" :loading="loading" label="Páginas do arquivo" previous-label="Anterior" next-label="Próxima" empty-label="Sem resultados" /></div></MCard><MemoryDetail :id="selected" @close="selected = null" @changed="changed" /></div>
</template>
