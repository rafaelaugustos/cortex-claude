import { createApp } from 'vue'
import { createMavisServices } from '@getcortexlabs/mavis-web/services'
import { mavis, midnight } from '@getcortexlabs/mavis-core'
import { Activity, Archive, ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Brain, ChartNoAxesCombined, Check, CheckCheck, ChevronDown, ChevronLeft, ChevronRight, ChevronUp, CircleAlert, CircleCheck, CircleX, Clock3, Folder, FileText, GitBranch, Inbox, Info, ListTodo, Menu, Moon, Network, PanelLeftClose, PanelLeftOpen, RefreshCw, Search, Settings2, ShieldCheck, Sun, ThumbsDown, ThumbsUp, Trash2, TriangleAlert, X, ZoomIn, ZoomOut, Maximize2 } from '@lucide/vue'
import '@getcortexlabs/mavis-web/base.css'
import './index.css'
import App from './App.vue'

let appearance: 'light' | 'dark' = 'light'
try { if (localStorage.getItem('cortex-theme') === 'dark') appearance = 'dark' } catch { /* Storage is optional. */ }
createApp(App).use(createMavisServices({
  theme: mavis, darkTheme: midnight, appearance, iconFallback: 'none',
  icons: { activity: Activity, archive: Archive, 'arrow-down': ArrowDown, 'arrow-left': ArrowLeft, 'arrow-right': ArrowRight, 'arrow-up': ArrowUp, brain: Brain, 'chart-no-axes-combined': ChartNoAxesCombined, check: Check, 'check-check': CheckCheck, 'chevron-down': ChevronDown, 'chevron-left': ChevronLeft, 'chevron-right': ChevronRight, 'chevron-up': ChevronUp, 'circle-alert': CircleAlert, 'circle-check': CircleCheck, 'circle-x': CircleX, 'clock-3': Clock3, clock: Clock3, folder: Folder, 'file-text': FileText, 'git-branch': GitBranch, inbox: Inbox, info: Info, 'list-todo': ListTodo, menu: Menu, moon: Moon, network: Network, 'panel-left-close': PanelLeftClose, 'panel-left-open': PanelLeftOpen, 'refresh-cw': RefreshCw, search: Search, 'settings-2': Settings2, 'shield-check': ShieldCheck, sun: Sun, 'thumbs-down': ThumbsDown, 'thumbs-up': ThumbsUp, 'trash': Trash2, 'triangle-alert': TriangleAlert, x: X, 'zoom-in': ZoomIn, 'zoom-out': ZoomOut, 'maximize-2': Maximize2 },
})).mount('#root')
