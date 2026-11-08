<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { MAlert, MBadge, MButton, MCard, MEmptyState, MInput, MPagination, MSheet } from '@getcortexlabs/mavis-web'
import { fetchExecutions, formatCount, formatDateTime, type ExecutionEntry } from '../lib/api'
const items = ref<ExecutionEntry[]>([]), total = ref(0), page = ref(1), query = ref(''), error = ref(''), loading = ref(true), open = ref(false)
const selected = ref<ExecutionEntry>()
let generation = 0
let debounce: ReturnType<typeof setTimeout>
async function load() { const request = ++generation; loading.value = true; try { const data = await fetchExecutions(query.value, (page.value - 1) * 30); if (request === generation) { items.value = data.items; total.value = data.total; error.value = '' } } catch (e) { if (request === generation) error.value = String(e) } finally { if (request === generation) loading.value = false } }
watch(query, () => { generation++; clearTimeout(debounce); debounce = setTimeout(() => { if (page.value !== 1) page.value = 1; else void load() }, 220) })
watch(page, load, { immediate: true })
onUnmounted(() => { generation++; clearTimeout(debounce) })
</script>
<template><div class="stack"><MInput v-model="query" label="Buscar no histórico" placeholder="Trecho de uma execução antiga…" type="search" icon="search" /><MAlert v-if="error" title="Não foi possível carregar o histórico" :description="error" tone="error"><template #actions><MButton @click="load">Tentar novamente</MButton></template></MAlert><p v-if="loading" role="status">Carregando histórico…</p><p v-else class="muted">{{ formatCount(total) }} registros preservados</p><MEmptyState v-if="!loading && !items.length" title="Nenhum registro encontrado" description="Execuções antigas identificadas durante a migração aparecem aqui." icon="clock" /><MCard v-for="item in items" :key="`${item._scope}:${item.id}`" interactive class="memory-preview" :accessibility-label="`Abrir registro ${item.id}`" @click="selected = item; open = true"><div class="row between wrap"><MBadge :text="item._scope" tone="neutral" size="sm" /><small>{{ formatDateTime(item.created_at) }}</small></div><p>{{ item.content.slice(0, 240) }}</p></MCard><MPagination v-if="total > 30" v-model="page" :total="total" :page-size="30" :loading="loading" label="Páginas do histórico" previous-label="Anterior" next-label="Próxima" /><MSheet v-model:open="open" title="Registro de execução" close-label="Fechar registro"><div class="sheet-content wide stack"><p class="muted">Preservado para consulta. Este conteúdo não é usado como memória.</p><pre class="execution-content">{{ selected?.content }}</pre></div></MSheet></div></template>
