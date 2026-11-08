<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { MAlert, MButton, MCard, MDialog, MEmptyState, MInput, MSelect } from '@getcortexlabs/mavis-web'
import type { ChoiceValue } from '@getcortexlabs/mavis-core'
import { executeCleanup, fetchClusters, formatSize, previewCleanup, type CleanupPreview, type CleanupRule, type Cluster, type Overview } from '../lib/api'
const props = defineProps<{ overview: Overview }>()
const emit = defineEmits<{ refresh: [] }>()
const type = ref<ChoiceValue | null>('tag')
const value = ref<ChoiceValue | null>(null)
const pattern = ref('')
const clusters = ref<Cluster[]>([])
const rules = ref<CleanupRule[]>([])
const preview = ref<CleanupPreview>()
const busy = ref(false)
const confirm = ref(false)
const error = ref('')
const notice = ref('')
const options = computed(() => type.value === 'tag' ? props.overview.tags.map(t => ({ value: t.name, label: `${t.name} (${t.count})` })) : type.value === 'scope' ? props.overview.scopes.map(s => ({ value: s.name, label: `${s.name} (${s.memories})` })) : clusters.value.map((c, i) => ({ value: i, label: `${c.label || 'Sem título'} · ${c.scope}` })))
watch(type, async next => { value.value = null; if (next === 'cluster') { try { clusters.value = (await fetchClusters({ limit: 200, sort: 'size' })).items } catch (e) { error.value = String(e) } } })
function label(rule: CleanupRule) { return `${({ tag: 'Tag', scope: 'Projeto', cluster: 'Grupo', pattern: 'Padrão' })[rule.type]}: ${rule.value}${rule.type === 'cluster' ? ` · ${rule.scope}` : ''}` }
function add() {
  let rule: CleanupRule
  if (type.value === 'pattern') { if (!pattern.value.trim()) return; try { new RegExp(pattern.value, 'i') } catch { error.value = 'Expressão regular inválida.'; return } rule = { type: 'pattern', value: pattern.value } }
  else if (type.value === 'cluster') { const cluster = clusters.value[Number(value.value)]; if (value.value === null || !cluster) return; rule = { type: 'cluster', value: cluster.id, scope: cluster.scope } }
  else { if (value.value === null) return; rule = { type: type.value === 'scope' ? 'scope' : 'tag', value: String(value.value) } }
  if (!rules.value.some(r => JSON.stringify(r) === JSON.stringify(rule))) rules.value.push(rule)
  preview.value = undefined; error.value = ''; notice.value = ''
}
async function calculate() { busy.value = true; error.value = ''; notice.value = ''; try { preview.value = await previewCleanup(rules.value) } catch (e) { error.value = String(e) } finally { busy.value = false } }
async function remove() { busy.value = true; error.value = ''; try { const result = await executeCleanup(rules.value); notice.value = `${result.deleted} memórias removidas.`; preview.value = undefined; rules.value = []; confirm.value = false; emit('refresh') } catch (e) { error.value = String(e); confirm.value = false; preview.value = undefined } finally { busy.value = false } }
</script>
<template>
  <div class="stack"><MAlert v-if="error" title="Não foi possível concluir" :description="error" tone="error" announce /><MAlert v-if="notice" :title="notice" tone="success" announce /><div class="two-columns"><MCard gap="lg"><h2>O que deseja remover?</h2><p class="muted">As regras se somam. Uma memória que corresponder a qualquer uma delas será incluída.</p><MSelect v-model="type" label="Tipo de regra" :options="[{ value: 'tag', label: 'Tag' }, { value: 'scope', label: 'Projeto inteiro' }, { value: 'cluster', label: 'Grupo de assuntos' }, { value: 'pattern', label: 'Padrão no conteúdo' }]" close-label="Fechar opções" :disabled="busy" /><MInput v-if="type === 'pattern'" v-model="pattern" label="Expressão regular" placeholder="Ex.: rascunho|temporário" :disabled="busy" /><MSelect v-else v-model="value" :options="options" label="Valor da regra" placeholder="Selecione um valor" close-label="Fechar opções" :disabled="busy" /><MButton variant="secondary" :disabled="busy || (type === 'pattern' ? !pattern.trim() : value === null)" @click="add">Adicionar regra</MButton><div v-if="rules.length" class="stack compact"><h3>Regras da prévia</h3><div v-for="(rule, i) in rules" :key="JSON.stringify(rule)" class="row between"><span>{{ label(rule) }}</span><MButton icon="x" variant="ghost" :accessibility-label="`Remover regra ${label(rule)}`" :disabled="busy" @click="rules.splice(i, 1); preview = undefined" /></div></div><MButton :disabled="!rules.length" :loading="busy" @click="calculate">Gerar prévia</MButton></MCard><MCard gap="lg"><h2>Prévia da limpeza</h2><MEmptyState v-if="!preview" compact title="Confira antes de remover" description="Adicione as regras e gere uma prévia para ver o alcance da limpeza." icon="archive" /><template v-else><strong class="metric-value">{{ preview.count }}</strong><p>memórias · {{ formatSize(preview.size) }} de conteúdo</p><dl class="facts"><div v-for="item in preview.by_scope" :key="item.scope"><dt>{{ item.scope }}</dt><dd>{{ item.count }}</dd></div></dl><h3 v-if="preview.sample.length">Amostra do conteúdo</h3><div v-for="item in preview.sample" :key="item.id" class="conclusion"><p>{{ item.content.slice(0, 200) }}</p><small>{{ item._scope }}</small></div><MButton icon="trash" :disabled="!preview.count || busy" @click="confirm = true">Remover memórias da prévia</MButton></template></MCard></div><MDialog v-model:open="confirm" title="Confirmar limpeza do arquivo?" :description="`A prévia encontrou ${preview?.count || 0} memórias. As memórias que corresponderem às regras e suas relações serão excluídas. Essa ação não pode ser desfeita.`" tone="danger" confirm-label="Excluir memórias" cancel-label="Cancelar" :loading="busy" @confirm="remove" /></div>
</template>
