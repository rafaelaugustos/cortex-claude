<script setup lang="ts">
import { ref, watch } from 'vue'
import { MAlert, MButton, MDialog, MInput, MSheet } from '@getcortexlabs/mavis-web'
import { deleteMemory, fetchMemory, formatDateTime, parseTags, updateMemory, type Fact, type Memory } from '../lib/api'
const props = defineProps<{ id: string | null }>()
const emit = defineEmits<{ close: []; changed: [] }>()
const open = ref(false)
const memory = ref<Memory>()
const facts = ref<Fact[]>([])
const content = ref('')
const tags = ref('')
const error = ref('')
const busy = ref(false)
const confirm = ref(false)
let request = 0
watch(() => props.id, async id => { const generation = ++request; open.value = !!id; memory.value = undefined; error.value = ''; if (!id) return; try { const data = await fetchMemory(id); if (request !== generation) return; memory.value = data.memory; facts.value = data.facts; content.value = data.memory.content; tags.value = parseTags(data.memory.tags).join(', ') } catch (e) { if (generation === request) error.value = String(e) } }, { immediate: true })
async function save() { if (!memory.value) return; busy.value = true; error.value = ''; try { await updateMemory(memory.value.id, { content: content.value, tags: tags.value.split(',').map(s => s.trim()).filter(Boolean) }); emit('changed'); emit('close') } catch (e) { error.value = String(e) } finally { busy.value = false } }
async function remove() { if (!memory.value) return; busy.value = true; try { await deleteMemory(memory.value.id); confirm.value = false; emit('changed'); emit('close') } catch (e) { error.value = String(e); confirm.value = false } finally { busy.value = false } }
</script>
<template>
  <MSheet :open="open" title="Memória do arquivo" close-label="Fechar memória" @update:open="value => { if (!value) emit('close') }"><div class="sheet-content stack"><MAlert v-if="error" title="Não foi possível concluir" :description="error" tone="error" announce /><p v-if="!memory && !error" role="status">Carregando memória…</p><template v-if="memory"><small>{{ memory._scope || memory.scope }} · {{ formatDateTime(memory.created_at) }}</small><MInput v-model="content" label="Conteúdo" multiline :rows="8" /><MInput v-model="tags" label="Tags" helper-text="Separe por vírgulas." /><div v-if="facts.length"><h3>Relações extraídas</h3><ul class="evidence-list"><li v-for="(fact, i) in facts" :key="i">{{ fact.subject }} → {{ fact.relation }} → {{ fact.object }}</li></ul></div><div class="row wrap"><MButton :loading="busy" :disabled="!content.trim()" @click="save">Salvar alterações</MButton><MButton variant="secondary" icon="trash" :disabled="busy" @click="confirm = true">Excluir memória</MButton></div></template></div></MSheet>
  <MDialog v-model:open="confirm" title="Excluir esta memória?" description="O conteúdo e as relações associadas serão removidos do arquivo." tone="danger" confirm-label="Excluir" cancel-label="Cancelar" :loading="busy" @confirm="remove" />
</template>
