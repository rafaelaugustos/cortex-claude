<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, onUnmounted, ref } from 'vue'
import { MAlert, MBadge, MButton, MIcon, MNavigationRail, MSheet, useMavisTokens } from '@getcortexlabs/mavis-web'
import { useMavisTheme } from '@getcortexlabs/mavis-core/vue'
import type { IconName, NavigationGroup } from '@getcortexlabs/mavis-core'
import { fetchLearning, fetchOverview, type LearningData, type Overview } from './lib/api'
import OverviewView from './views/OverviewView.vue'
import LearningView from './views/LearningView.vue'
const ReviewView = defineAsyncComponent(() => import('./views/ReviewView.vue'))
const TasksView = defineAsyncComponent(() => import('./views/TasksView.vue'))
const ArchiveView = defineAsyncComponent(() => import('./views/ArchiveView.vue'))
const ClustersView = defineAsyncComponent(() => import('./views/ClustersView.vue'))
const CleanupView = defineAsyncComponent(() => import('./views/CleanupView.vue'))
const ProjectsView = defineAsyncComponent(() => import('./views/ProjectsView.vue'))
const HistoryView = defineAsyncComponent(() => import('./views/HistoryView.vue'))
const HealthView = defineAsyncComponent(() => import('./views/HealthView.vue'))
const tokens = useMavisTokens()
const theme = useMavisTheme()
const dark = computed(() => theme.theme.value.appearance === 'dark')
const learning = ref<LearningData>()
const overview = ref<Overview>()
const error = ref('')
const loading = ref(false)
const mobileOpen = ref(false)
const collapsed = ref(false)
const route = ref(location.hash.slice(1) || 'overview')
const revision = ref(0)
const destinations: { key: string; label: string; icon: IconName; description: string }[] = [
  { key: 'overview', label: 'Visão geral', icon: 'activity', description: 'O que você já ensinou. O que vale lembrar.' },
  { key: 'learning', label: 'Aprendizados', icon: 'brain', description: 'Uma memória compartilhada, com contexto para cada escolha.' },
  { key: 'projects', label: 'Projetos', icon: 'folder', description: 'O que cada projeto faz, como funciona e de onde veio esse conhecimento.' },
  { key: 'tasks', label: 'Retomar tarefas', icon: 'list-todo', description: 'Objetivo, decisões e próximo passo, sem começar do zero.' },
  { key: 'review', label: 'Revisar conflitos', icon: 'git-branch', description: 'Você decide qual conclusão faz sentido e quando ela se aplica.' },
  { key: 'evaluation', label: 'Economia & qualidade', icon: 'chart-no-axes-combined', description: 'Compare consumo real, qualidade e o contexto que deixou de se repetir.' },
  { key: 'archive', label: 'Arquivo', icon: 'archive', description: 'Encontre e edite o conteúdo salvo nas suas conversas.' },
  { key: 'clusters', label: 'Conexões', icon: 'network', description: 'Explore os assuntos e as relações entre suas memórias.' },
  { key: 'cleanup', label: 'Limpeza', icon: 'trash', description: 'Revise uma prévia antes de remover o que não precisa mais.' },
  { key: 'history', label: 'Histórico de execução', icon: 'clock', description: 'Registros antigos preservados para consulta. Fora da busca de memórias e do contexto automático.' },
  { key: 'health', label: 'Saúde & recuperação', icon: 'shield-check', description: 'Saiba o que foi salvo, acompanhe pendências e confira seus backups.' },
]
const current = computed(() => destinations.find(d => d.key === route.value) || destinations[0]!)
const groups = computed<NavigationGroup[]>(() => [
  { key: 'memory', label: 'Sua memória', items: destinations.slice(0, 6).map(item) },
  { key: 'library', label: 'Biblioteca', items: destinations.slice(6).map(item) },
])
function item(d: typeof destinations[number]) {
  return { value: d.key, label: d.key === 'review' ? 'Conflitos' : d.key === 'evaluation' ? 'Economia de tokens' : d.label, icon: d.icon, href: `#${d.key}`, badge: d.key === 'review' && learning.value?.stats.conflicts_open ? learning.value.stats.conflicts_open : undefined, navigate: () => go(d.key) }
}
function go(key: string) { location.hash = key; route.value = key; mobileOpen.value = false }
function syncRoute() { route.value = location.hash.slice(1) || 'overview'; mobileOpen.value = false }
function toggleTheme() {
  const value = dark.value ? 'light' : 'dark'
  theme.setAppearance(value)
  try { localStorage.setItem('cortex-theme', value) } catch { /* Optional preference. */ }
}
async function refresh() {
  if (loading.value) return
  loading.value = true
  try { [learning.value, overview.value] = await Promise.all([fetchLearning(), fetchOverview()]); error.value = '' }
  catch (e) { error.value = e instanceof Error ? e.message : 'Não foi possível atualizar os dados.' }
  finally { loading.value = false; revision.value++ }
}
let interval: ReturnType<typeof setInterval>
onMounted(() => { void refresh(); window.addEventListener('hashchange', syncRoute); interval = setInterval(() => { if (!document.hidden) void refresh() }, 15000) })
onUnmounted(() => { clearInterval(interval); window.removeEventListener('hashchange', syncRoute) })
</script>

<template>
  <div class="app" :style="tokens" :data-theme="dark ? 'dark' : 'light'">
    <a class="skip-link" href="#content">Pular para o conteúdo</a>
    <aside class="desktop-nav">
      <MNavigationRail v-model:collapsed="collapsed" :model-value="current.key" :groups="groups" label="Navegação principal" collapse-label="Recolher menu" expand-label="Expandir menu">
        <template #header><a class="brand" href="#overview" aria-label="Cortex, visão geral"><span class="brand-mark"><MIcon name="brain" :size="25" /></span><span v-if="!collapsed">cortex<span class="brand-sub">Memória que acompanha você</span></span></a></template>
        <template #footer><div class="rail-footer"><MBadge :text="collapsed ? 'Local' : 'Tudo fica neste computador'" tone="success" size="sm" /><small v-if="!collapsed">Uma memória. Todos os projetos.</small></div></template>
      </MNavigationRail>
    </aside>
    <div class="workspace">
      <header class="topbar">
        <div class="row"><MButton class="mobile-menu" icon="menu" variant="ghost" accessibility-label="Abrir navegação" @click="mobileOpen = true" /><span class="topbar-label">CORTEX <span>/</span> {{ current.label }}</span></div>
        <div class="row"><MBadge text="Local" tone="success" size="sm" /><MButton :icon="dark ? 'sun' : 'moon'" variant="ghost" :accessibility-label="dark ? 'Usar tema claro' : 'Usar tema escuro'" @click="toggleTheme" /><MButton icon="refresh-cw" variant="ghost" accessibility-label="Atualizar dados" :loading="loading" @click="refresh" /></div>
      </header>
      <main id="content" tabindex="-1">
        <div class="page-title"><div><p class="eyebrow">{{ ['archive', 'clusters', 'cleanup'].includes(current.key) ? 'BIBLIOTECA' : 'SUA MEMÓRIA' }}</p><h1>{{ current.label }}</h1><p class="muted">{{ current.description }}</p></div><MBadge v-if="current.key === 'learning' && learning" :text="`${learning.lessons.length} aprendizados`" tone="primary" class="page-count" /></div>
        <MAlert v-if="error" title="Não foi possível atualizar" :description="error" tone="error" announce><template #actions><MButton variant="secondary" @click="refresh">Tentar novamente</MButton></template></MAlert>
        <HealthView v-if="current.key === 'health'" :revision="revision" />
        <div v-else-if="!learning || !overview" class="loading-state" role="status">{{ error ? 'Aguardando conexão com o Cortex.' : 'Carregando sua memória…' }}</div>
        <template v-else>
          <OverviewView v-if="current.key === 'overview' || current.key === 'evaluation'" :learning="learning" :overview="overview" :evaluation="current.key === 'evaluation'" @navigate="go" />
          <LearningView v-else-if="current.key === 'learning'" :data="learning" @refresh="refresh" @review="go('review')" />
          <ProjectsView v-else-if="current.key === 'projects'" :revision="revision" @refresh="refresh" />
          <HistoryView v-else-if="current.key === 'history'" />
          <TasksView v-else-if="current.key === 'tasks'" :revision="revision" @refresh="refresh" />
          <ReviewView v-else-if="current.key === 'review'" :revision="revision" @refresh="refresh" />
          <ArchiveView v-else-if="current.key === 'archive'" :overview="overview" @refresh="refresh" />
          <ClustersView v-else-if="current.key === 'clusters'" :overview="overview" />
          <CleanupView v-else-if="current.key === 'cleanup'" :overview="overview" @refresh="refresh" />
        </template>
        <footer class="page-footer"><span>Cortex · memória local</span><span>Feito com Mavis Web</span></footer>
      </main>
    </div>
    <MSheet v-model:open="mobileOpen" title="Navegar pelo Cortex" close-label="Fechar navegação"><div class="mobile-links"><MButton v-for="d in destinations" :key="d.key" :icon="d.icon" :variant="current.key === d.key ? 'primary' : 'ghost'" @click="go(d.key)">{{ d.label }}</MButton></div></MSheet>
  </div>
</template>
