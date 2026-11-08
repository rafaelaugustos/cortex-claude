<script setup lang="ts">
import { ref, watch } from 'vue'
import { MAlert, MBadge, MButton, MCard, MDialog, MEmptyState, MInput, MSelect, MSheet } from '@getcortexlabs/mavis-web'
import type { ChoiceValue } from '@getcortexlabs/mavis-core'
import { fetchConflicts, formatDateTime, resolveConflict, type Conflict } from '../lib/api'
const props = defineProps<{ revision: number }>()
const emit = defineEmits<{ refresh: [] }>()
const items = ref<Conflict[]>([])
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const selected = ref<Conflict>()
const open = ref(false)
const confirm = ref(false)
const choice = ref<ChoiceValue | null>('keep_left')
const condition = ref('')
const exclude = ref('')
const options = [{ value: 'keep_left', label: 'Manter a conclusão A' }, { value: 'keep_right', label: 'Manter a conclusão B' }, { value: 'condition_left', label: 'Usar A somente em uma condição' }, { value: 'condition_right', label: 'Usar B somente em uma condição' }]
let request = 0
async function load() { const generation = ++request; try { const data = await fetchConflicts(); if (generation === request) { items.value = data.items; error.value = '' } } catch (e) { if (generation === request) error.value = String(e) } finally { if (generation === request) loading.value = false } }
watch(() => props.revision, load, { immediate: true })
function inspect(item: Conflict) { selected.value = item; choice.value = 'keep_left'; condition.value = ''; exclude.value = ''; error.value = ''; open.value = true }
async function settle() {
  if (!selected.value) return
  busy.value = true; error.value = ''
  try { await resolveConflict(selected.value.id, String(choice.value), String(choice.value).startsWith('condition') ? { all: condition.value.split(',').map(s => s.trim()).filter(Boolean), none: exclude.value.split(',').map(s => s.trim()).filter(Boolean) } : undefined); confirm.value = false; open.value = false; notice.value = 'Decisão salva. A próxima seleção usará a regra revisada.'; await load(); emit('refresh') }
  catch (e) { error.value = String(e); confirm.value = false } finally { busy.value = false }
}
function conditions(raw: string) { try { return Object.entries(JSON.parse(raw)).map(([key, value]) => `${({ all: 'Todos', any: 'Qualquer um', none: 'Exceto' } as Record<string, string>)[key] || key}: ${(value as string[]).join(', ')}`).join(' · ') || 'Sem condição específica' } catch { return raw } }
</script>
<template>
  <div class="stack">
    <MAlert v-if="notice" :title="notice" tone="success" announce />
    <MAlert v-if="error && !open" title="Não foi possível carregar os conflitos" :description="error" tone="error"><template #actions><MButton @click="load">Tentar novamente</MButton></template></MAlert>
    <p v-if="loading" role="status">Carregando conflitos…</p>
    <MEmptyState v-else-if="!items.length && !error" title="Nenhum conflito pendente" description="Se duas conclusões divergirem sobre o mesmo assunto, você poderá revisá-las aqui." icon="shield-check" />
    <MCard v-for="item in items" :key="item.id" gap="lg"><div class="row between wrap"><div><MBadge text="Aguardando decisão" tone="warning" /><h2 class="space-top">{{ item.topic }}</h2></div><small>{{ formatDateTime(item.created_at * 1000) }}</small></div><div class="two-columns"><div class="conclusion"><small>CONCLUSÃO A</small><p>{{ item.left_content }}</p><small>{{ item.left_evidence.length }} observações</small></div><div class="conclusion"><small>CONCLUSÃO B</small><p>{{ item.right_content }}</p><small>{{ item.right_evidence.length }} observações</small></div></div><div class="row between wrap"><p class="muted">As duas regras ficam fora do contexto automático.</p><MButton @click="inspect(item)">Revisar conclusões</MButton></div></MCard>
    <MSheet v-model:open="open" title="Resolver conflito" close-label="Fechar revisão"><div v-if="selected" class="sheet-content stack"><MAlert v-if="error" title="Não foi possível salvar a decisão" :description="error" tone="error" announce /><div v-for="side in (['left', 'right'] as const)" :key="side" class="conclusion"><h3>Conclusão {{ side === 'left' ? 'A' : 'B' }}</h3><p>{{ selected[`${side}_content`] }}</p><p class="muted">{{ conditions(selected[`${side}_conditions`]) }}</p><ul class="evidence-list"><li v-for="(evidence, i) in selected[`${side}_evidence`]" :key="i"><span>{{ evidence.origin }}</span><small>{{ evidence.source }} · {{ formatDateTime(evidence.observed_at * 1000) }}</small></li></ul></div><MSelect v-model="choice" label="Como resolver" :options="options" close-label="Fechar opções" /><template v-if="String(choice).startsWith('condition')"><MInput v-model="condition" label="Aplicar quando aparecerem estes termos" placeholder="Ex.: arquitetura, legado" helper-text="Separe por vírgulas. Todos os termos precisam estar no pedido." /><MInput v-model="exclude" label="Exceto quando aparecerem" placeholder="Termos opcionais, separados por vírgulas" /></template><MButton :disabled="String(choice).startsWith('condition') && !condition.trim()" @click="confirm = true">Aplicar decisão</MButton></div></MSheet>
    <MDialog v-model:open="confirm" title="Confirmar esta decisão?" :description="String(choice).startsWith('condition') ? 'A regra escolhida será usada somente quando a condição combinar com a tarefa.' : 'A conclusão escolhida será mantida. A outra ficará marcada como substituída.'" confirm-label="Confirmar decisão" cancel-label="Voltar" :loading="busy" @confirm="settle" />
  </div>
</template>
