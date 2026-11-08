<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { MAlert, MBadge, MButton, MCard, MDialog, MEmptyState, MInput, MSheet } from '@getcortexlabs/mavis-web'
import { changeTask, fetchTasks, formatDateTime, type WorkItem } from '../lib/api'
const props = defineProps<{ revision: number }>()
const emit = defineEmits<{ refresh: [] }>()
const items = ref<WorkItem[]>([])
const query = ref('')
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const selected = ref<WorkItem>()
const open = ref(false)
const confirm = ref(false)
const action = ref<'complete' | 'forget'>('complete')
const filtered = computed(() => items.value.filter(item => `${item.title} ${item.origin}`.toLocaleLowerCase().includes(query.value.toLocaleLowerCase())))
let request = 0
async function load() { const generation = ++request; try { const result = await fetchTasks(); if (request === generation) { items.value = result.items; error.value = '' } } catch (e) { if (request === generation) error.value = String(e) } finally { if (request === generation) loading.value = false } }
watch(() => props.revision, load, { immediate: true })
async function update() { if (!selected.value) return; busy.value = true; try { await changeTask(selected.value, action.value); confirm.value = false; open.value = false; await load(); emit('refresh') } catch (e) { error.value = String(e); confirm.value = false } finally { busy.value = false } }
</script>
<template>
  <div class="stack">
    <MInput v-model="query" label="Buscar tarefas" placeholder="Título ou projeto…" type="search" icon="search" />
    <MAlert v-if="error && !open" title="Não foi possível carregar as tarefas" :description="error" tone="error"><template #actions><MButton @click="load">Tentar novamente</MButton></template></MAlert>
    <p v-if="loading" role="status">Carregando tarefas…</p>
    <MEmptyState v-else-if="!filtered.length && !error" title="Nenhuma tarefa por aqui" description="Ao salvar um ponto de retomada na conversa, o objetivo, as decisões e o próximo passo ficam disponíveis aqui." icon="list-todo" />
    <div class="lesson-grid"><MCard v-for="item in filtered" :key="item.id" gap="md"><div class="row between wrap"><MBadge :text="item.state === 'complete' ? 'Concluída' : item.needs_review ? 'Revisar arquivos' : 'Em andamento'" :tone="item.state === 'complete' ? 'success' : item.needs_review ? 'warning' : 'accent'" /><small>Revisão {{ item.revision }}</small></div><small v-if="item.source === 'automatic'" class="muted">Retomada automática · {{ item.client === 'codex' ? 'Codex' : 'Claude Code' }}</small><h2>{{ item.title }}</h2><p>{{ item.summary }}</p><div class="next-step"><small>PRÓXIMO PASSO</small><p>{{ item.next_step }}</p></div><small class="path">{{ item.origin }}</small><MButton variant="secondary" @click="selected = item; open = true; error = ''">Ver ponto de retomada</MButton></MCard></div>
    <MSheet v-model:open="open" title="Ponto de retomada" close-label="Fechar tarefa"><div v-if="selected" class="sheet-content stack"><MAlert v-if="error" title="Não foi possível atualizar a tarefa" :description="error" tone="error" announce /><MAlert v-if="selected.source === 'automatic'" title="Ponto de retomada parcial" description="Capturado automaticamente. O relato do assistente não confirma que testes passaram ou que o trabalho terminou." tone="info" /><h2>{{ selected.title }}</h2><p>{{ selected.summary }}</p><MAlert v-if="selected.needs_review" title="Confira os arquivos antes de retomar" description="Os arquivos mudaram ou o ponto de retomada venceu. Ele não será inserido automaticamente na conversa." tone="warning" /><div v-if="selected.decisions.length"><h3>Decisões tomadas</h3><ul><li v-for="item in selected.decisions" :key="item">{{ item }}</li></ul></div><div v-if="selected.pending.length"><h3>O que falta</h3><ul><li v-for="item in selected.pending" :key="item">{{ item }}</li></ul></div><div class="next-step"><h3>Próximo passo</h3><p>{{ selected.next_step }}</p></div><p class="muted">Peça para retomar esta tarefa na conversa do projeto. O Cortex usa este resumo se ele ainda estiver válido.</p><small class="path">{{ selected.origin }} · {{ formatDateTime(selected.updated_at * 1000) }}</small><div class="row wrap"><MButton v-if="selected.state === 'open'" icon="check" @click="action = 'complete'; confirm = true">Marcar como concluída</MButton><MButton variant="secondary" icon="trash" @click="action = 'forget'; confirm = true">Esquecer tarefa</MButton></div></div></MSheet>
    <MDialog v-model:open="confirm" :title="action === 'complete' ? 'Concluir esta tarefa?' : 'Esquecer esta tarefa?'" :description="action === 'complete' ? 'Ela deixará de aparecer como sugestão de retomada.' : 'O resumo e as decisões salvas serão removidos.'" :tone="action === 'forget' ? 'danger' : 'default'" :confirm-label="action === 'complete' ? 'Concluir' : 'Esquecer'" cancel-label="Cancelar" :loading="busy" @confirm="update" />
  </div>
</template>
