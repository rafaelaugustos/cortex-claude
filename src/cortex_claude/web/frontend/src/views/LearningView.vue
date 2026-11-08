<script setup lang="ts">
import { computed, ref } from 'vue'
import { MAlert, MBadge, MButton, MCard, MDialog, MEmptyState, MInput, MSelect, MSheet } from '@getcortexlabs/mavis-web'
import type { ChoiceValue } from '@getcortexlabs/mavis-core'
import { assessLesson, fetchLesson, forgetLesson, formatDateTime, type LearningData, type Lesson, type LessonDetail } from '../lib/api'
const props = defineProps<{ data: LearningData }>()
const emit = defineEmits<{ refresh: []; review: [] }>()
const query = ref('')
const state = ref<ChoiceValue | null>('all')
const states = [{ value: 'all', label: 'Todos os estados' }, { value: 'active', label: 'Compartilhados' }, { value: 'candidate', label: 'Em observação' }, { value: 'stale', label: 'Revalidar' }, { value: 'superseded', label: 'Substituídos' }]
const labels: Record<string, string> = { active: 'Compartilhado', candidate: 'Em observação', stale: 'Revalidar', superseded: 'Substituído' }
const filtered = computed(() => props.data.lessons.filter(l => (state.value === 'all' || l.state === state.value) && `${l.content} ${l.topic}`.toLocaleLowerCase().includes(query.value.toLocaleLowerCase())))
const selected = ref<Lesson>()
const detail = ref<LessonDetail>()
const open = ref(false)
const confirm = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
let request = 0
async function inspect(lesson: Lesson) {
  selected.value = lesson; detail.value = undefined; open.value = true; error.value = ''
  const id = ++request
  try { const value = await fetchLesson(lesson.id); if (id === request) detail.value = value }
  catch (e) { if (id === request) error.value = String(e) }
}
async function assess(lesson: Lesson, assessment: 'useful' | 'irrelevant') {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try { await assessLesson(lesson.id, assessment); notice.value = 'Feedback salvo. A utilidade será considerada nas próximas seleções.'; emit('refresh') }
  catch (e) { error.value = String(e) } finally { busy.value = false }
}
async function forget() {
  if (!selected.value) return
  busy.value = true
  try { await forgetLesson(selected.value.id); confirm.value = false; open.value = false; notice.value = 'Aprendizado removido.'; emit('refresh') }
  catch (e) { error.value = String(e) } finally { busy.value = false }
}
</script>

<template>
  <div class="stack">
    <div class="filters"><MInput v-model="query" label="Buscar aprendizados" placeholder="Assunto ou preferência…" icon="search" type="search" /><MSelect v-model="state" label="Estado" :options="states" close-label="Fechar opções" /></div>
    <MAlert v-if="notice" :title="notice" tone="success" announce dismissible close-label="Fechar mensagem" @close="notice = ''" />
    <MAlert v-if="error && !open" title="Não foi possível concluir" :description="error" tone="error" announce />
    <MEmptyState v-if="!filtered.length" :title="data.lessons.length ? 'Nenhum aprendizado encontrado' : 'Sua memória começa nas conversas'" :description="data.lessons.length ? 'Tente outro termo ou estado.' : 'Preferências e soluções confirmadas aparecem aqui conforme você trabalha.'" icon="brain" />
    <div v-else class="lesson-grid"><MCard v-for="lesson in filtered" :key="lesson.id" gap="md" class="lesson-card"><div class="row between wrap"><MBadge :text="lesson.has_conflict ? 'Em revisão' : labels[lesson.state]!" :tone="lesson.has_conflict ? 'warning' : lesson.state === 'active' ? 'success' : 'neutral'" /><small>{{ lesson.kind === 'experience' ? 'Solução aprendida' : 'Preferência' }}</small></div><p class="lesson-content">{{ lesson.content }}</p><div class="row wrap"><MBadge v-if="lesson.conditions !== '{}'" text="Tem condições" tone="accent" size="sm" /><small>{{ lesson.confirmations }} confirmações · {{ lesson.contexts }} contextos</small></div><div class="lesson-actions"><MButton variant="secondary" size="sm" @click="inspect(lesson)">Ver detalhes</MButton><div class="row"><MButton icon="thumbs-up" variant="ghost" size="sm" :disabled="busy" :accessibility-label="`Foi útil: ${lesson.content}`" @click="assess(lesson, 'useful')" /><MButton icon="thumbs-down" variant="ghost" size="sm" :disabled="busy" :accessibility-label="`Pouco útil: ${lesson.content}`" @click="assess(lesson, 'irrelevant')" /></div></div></MCard></div>
    <MSheet v-model:open="open" title="Detalhes do aprendizado" close-label="Fechar detalhes"><div v-if="selected" class="sheet-content stack"><MAlert v-if="error" title="Não foi possível concluir" :description="error" tone="error" announce /><h2>{{ selected.content }}</h2><MAlert v-if="selected.has_conflict" title="Aguardando revisão" description="Este aprendizado fica fora do contexto automático até resolver o conflito." tone="warning"><template #actions><MButton @click="open = false; emit('review')">Revisar conflito</MButton></template></MAlert><p v-if="!detail" role="status">Carregando detalhes…</p><template v-else><dl class="facts"><div><dt>Estado</dt><dd>{{ labels[selected.state] }}</dd></div><div><dt>Validação</dt><dd>{{ ({ passed: 'Testado', failed: 'Falhou', pending: 'Pendente', 'not-required': 'Não exigida' })[selected.validation] }}</dd></div><div v-if="selected.stale_reason"><dt>Revalidar</dt><dd>{{ selected.stale_reason }}</dd></div></dl><div v-for="(value, key) in detail.details" :key="key"><h3>{{ ({ situation: 'Situação', cause: 'Causa', solution: 'Solução' } as Record<string, string>)[key] || key }}</h3><p class="prewrap">{{ value }}</p></div><div v-if="Object.keys(detail.conditions).length"><h3>Quando se aplica</h3><dl class="facts"><div v-for="(values, key) in detail.conditions" :key="key"><dt>{{ ({ all: 'Todos', any: 'Qualquer um', none: 'Exceto' } as Record<string, string>)[key] || key }}</dt><dd>{{ values.join(', ') }}</dd></div></dl></div><div><h3>Observações de origem</h3><ul class="evidence-list"><li v-for="(evidence, index) in detail.evidence" :key="index"><span>{{ evidence.origin }}</span><small>{{ evidence.source }} · {{ formatDateTime(evidence.observed_at * 1000) }}</small></li></ul></div><div v-if="Object.keys(detail.dependencies).length"><h3>Arquivos de referência</h3><ul><li v-for="(_, path) in detail.dependencies" :key="path"><code>{{ path }}</code></li></ul></div><div v-if="detail.outcomes.length"><h3>Resultados observados</h3><ul class="evidence-list"><li v-for="(outcome, index) in detail.outcomes" :key="index"><span>{{ outcome.outcome === 'passed' ? 'Passou' : outcome.outcome === 'failed' ? 'Falhou' : outcome.outcome }} · {{ outcome.command || outcome.origin }}</span><small>{{ formatDateTime(outcome.observed_at * 1000) }}</small></li></ul></div><MButton icon="trash" variant="secondary" @click="confirm = true">Esquecer aprendizado</MButton></template></div></MSheet>
    <MDialog v-model:open="confirm" title="Esquecer este aprendizado?" description="O conteúdo e as evidências associadas serão removidos da memória compartilhada." tone="danger" confirm-label="Esquecer" cancel-label="Cancelar" :loading="busy" @confirm="forget" />
  </div>
</template>
