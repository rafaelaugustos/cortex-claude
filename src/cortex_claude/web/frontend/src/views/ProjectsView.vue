<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { MAlert, MBadge, MButton, MCard, MEmptyState, MInput, MSheet } from '@getcortexlabs/mavis-web'
import { fetchProjects, refreshProject, formatDateTime, type ProjectMemory } from '../lib/api'
const props = defineProps<{ revision: number }>()
const emit = defineEmits<{ refresh: [] }>()
const items = ref<ProjectMemory[]>([])
const origin = ref('')
const query = ref('')
const error = ref('')
const busy = ref(false)
const loading = ref(true)
const open = ref(false)
const selectedOrigin = ref('')
const selected = computed(() => items.value.find(item => item.origin === selectedOrigin.value))
const filtered = computed(() => items.value.filter(item => `${item.name} ${item.origin} ${item.purpose}`.toLowerCase().includes(query.value.toLowerCase())))
const sections: Record<string, string> = { purpose: 'Propósito', architecture: 'Arquitetura', conventions: 'Convenções', decisions: 'Decisões' }
let generation = 0
async function load() { const request = ++generation; try { const data = await fetchProjects(); if (request === generation) items.value = data.items } catch (e) { if (request === generation) error.value = String(e) } finally { if (request === generation) loading.value = false } }
watch(() => props.revision, load, { immediate: true })
async function refresh(path: string) {
  busy.value = true; error.value = ''
  try { const data = await refreshProject(path.trim()); if ('status' in data) throw new Error('A leitura de projetos está desativada na configuração.'); await load(); selectedOrigin.value = data.origin; origin.value = ''; open.value = true; emit('refresh') }
  catch (e) { error.value = String(e) } finally { busy.value = false }
}
</script>
<template>
  <div class="stack">
    <MCard gap="md"><h2>Conhecimento com origem</h2><p>O Cortex lê a estrutura e extrai símbolos e chamadas do código. Alterações atualizam somente os arquivos afetados no mapa. Durante o trabalho, o assistente registra conclusões com os arquivos que as sustentam. Tudo fica na mesma memória compartilhada.</p></MCard>
    <form class="project-form" @submit.prevent="refresh(origin)"><MInput v-model="origin" label="Caminho do projeto" placeholder="/Users/voce/projetos/meu-app" :autocorrect="false" /><MButton type="submit" icon="folder" :loading="busy" :disabled="!origin.trim()">Ler projeto</MButton></form>
    <MAlert v-if="error && !open" title="Não foi possível ler o projeto" :description="error" tone="error" announce />
    <MInput v-model="query" label="Buscar projetos" placeholder="Nome, caminho ou propósito…" icon="search" type="search" />
    <p v-if="loading" role="status">Carregando projetos…</p>
    <MEmptyState v-else-if="!filtered.length" title="Seu próximo projeto começa aqui" description="Abra uma sessão do Claude no projeto ou informe o caminho acima para ler sua estrutura." icon="folder" />
    <div class="lesson-grid"><MCard v-for="item in filtered" :key="item.origin" gap="md"><div class="row between wrap"><MBadge :text="item.needs_review || item.notes.some(note => note.needs_review) ? 'Arquivos alterados' : item.notes.length ? 'Com conclusões' : 'Estrutura lida'" :tone="item.needs_review || item.notes.some(note => note.needs_review) ? 'warning' : 'accent'" /><small>{{ item.modules.length }} módulos</small></div><h2>{{ item.name }}</h2><p>{{ item.purpose || 'Propósito ainda não sintetizado pelo assistente.' }}</p><div class="row wrap"><MBadge v-for="stack in [...new Set(item.modules.flatMap(module => module.stack))].slice(0, 7)" :key="stack" :text="stack" tone="neutral" size="sm" /></div><small class="path">{{ item.origin }}</small><MButton variant="secondary" @click="selectedOrigin = item.origin; open = true; error = ''">Explorar projeto</MButton></MCard></div>
    <MSheet v-model:open="open" :title="selected?.name || 'Projeto'" close-label="Fechar projeto"><div v-if="selected" class="sheet-content wide stack">
      <MAlert v-if="error" title="Não foi possível atualizar" :description="error" tone="error" />
      <p class="path">{{ selected.origin }}</p><p>{{ selected.purpose }}</p>
      <MAlert v-if="selected.needs_review" title="A estrutura mudou" description="Atualize a leitura dos arquivos. Conclusões com fontes alteradas precisam ser revisadas pelo assistente." tone="warning" />
      <div class="row between wrap"><small>Leitura {{ formatDateTime(selected.updated_at * 1000) }}</small><MButton variant="secondary" icon="refresh-cw" :loading="busy" @click="refresh(selected.origin)">Atualizar estrutura</MButton></div>
      <h2>O que aprendemos</h2><MEmptyState v-if="!selected.notes.length" title="A estrutura é o começo" description="Na conversa, peça ao Claude para entender a arquitetura e registrar o que aprendeu sobre este projeto. Cada conclusão deve citar arquivos de apoio." icon="brain" />
      <MCard v-for="note in selected.notes" :key="note.id" gap="md"><div class="row between wrap"><MBadge :text="sections[note.section] || note.section" tone="primary" /><MBadge v-if="note.needs_review" text="Revisar conclusão" tone="warning" /></div><p class="conclusion">{{ note.content }}</p><small>Síntese do assistente · fontes</small><ul class="source-list"><li v-for="source in note.sources" :key="source"><code>{{ source }}</code></li></ul><small v-if="note.needs_review" class="muted">A fonte mudou. Esta conclusão fica fora do contexto automático até ser revista.</small></MCard>
      <section v-if="selected.analysis" class="stack"><h2>Mapa do código</h2><p>{{ selected.analysis.coverage.analyzed }} de {{ selected.analysis.coverage.discovered }} arquivos compatíveis analisados · {{ selected.analysis.scan.reused_files }} reutilizados na última atualização · {{ selected.analysis.scan.read_files }} relidos.</p><p class="muted">Símbolos e chamadas encontrados no código. Chamadas são relações estáticas possíveis; fluxos de negócio e decisões precisam das conclusões com fontes acima.</p><MAlert v-if="selected.analysis.coverage.partial || selected.analysis.coverage.parser_unavailable" title="Cobertura parcial" description="Alguns arquivos ficaram fora dos limites de análise ou precisam do parser opcional. A memória não cobre o projeto inteiro." tone="warning" /><MAlert v-if="selected.review_queue?.length" title="Conclusões aguardando revisão" :description="`${selected.review_queue.length} conclusões possuem fontes alteradas. Atualizar o mapa não confirma essas conclusões.`" tone="warning" /><p v-if="selected.changed_files?.length" class="muted">{{ selected.changed_files.length }} arquivos mudaram desde a leitura; suas chamadas antigas foram retiradas deste mapa.</p><MCard v-for="file in selected.analysis.files.slice(0, 20)" :key="file.path" gap="sm"><h3 class="path">{{ file.path }}</h3><p>{{ file.symbols.map(symbol => symbol.name).join(', ') || 'Sem símbolos identificados' }}</p><small v-if="file.status !== 'parsed'">Análise indisponível para este arquivo.</small></MCard><p v-if="selected.analysis.files.length > 20" class="muted">Exibindo os primeiros 20 arquivos. Consulte o contexto do projeto para explorar os demais.</p><h3 v-if="selected.analysis.flows.length">Chamadas encontradas</h3><ul class="source-list"><li v-for="(flow, index) in selected.analysis.flows.slice(0, 24)" :key="index"><code>{{ flow.caller }} → {{ flow.callee }}</code><small>{{ flow.path }}:{{ flow.line }} · {{ flow.resolution === 'same-file-candidate' ? 'possível destino no mesmo arquivo' : 'destino não resolvido' }}</small></li></ul></section>
      <h2>Estrutura declarada</h2><p class="muted">Informações lidas dos arquivos de configuração. Os comandos abaixo não foram executados por esta leitura.</p>
      <MCard v-for="module in selected.modules" :key="module.manifest" gap="md"><h3>{{ module.name }}</h3><small class="path">{{ module.path }}</small><p v-if="module.purpose">{{ module.purpose }}</p><div class="row wrap"><MBadge v-for="stack in module.stack" :key="stack" :text="stack" tone="neutral" size="sm" /></div><dl class="project-commands"><template v-for="command in module.commands" :key="command.name"><dt>{{ command.name }}</dt><dd><code>{{ command.command }}</code><small>{{ command.definition }}</small></dd></template></dl><div v-if="module.entrypoints.length"><h4>Pontos de entrada</h4><ul class="source-list"><li v-for="entry in module.entrypoints" :key="entry"><code>{{ entry }}</code></li></ul></div><small class="path">Fonte: {{ module.manifest }}</small></MCard>
      <div v-if="selected.documents.length"><h3>Documentação encontrada</h3><ul class="source-list"><li v-for="doc in selected.documents" :key="doc.path"><code>{{ doc.path }}</code></li></ul></div>
      <MAlert v-if="selected.truncated || selected.warnings.length" title="Leitura parcial" description="O limite de leitura foi atingido ou alguns arquivos não puderam ser lidos. Explore os módulos relevantes na conversa para aprofundar o conhecimento." tone="warning" />
    </div></MSheet>
  </div>
</template>
