import { h } from 'vue'
import DefaultTheme from 'vitepress/theme'
import PlatformBadge from './PlatformBadge.vue'
import OrbitSignature from './OrbitSignature.vue'
import Fact from './Fact.vue'
import './custom.css'
import './orbit-signature.css'

export default {
  extends: DefaultTheme,
  Layout: () => h(DefaultTheme.Layout, null, {
    'nav-bar-title-after': () => h(PlatformBadge),
    'layout-bottom': () => h(OrbitSignature)
  }),
  enhanceApp({ app }) {
    app.component('Fact', Fact)
  }
}
