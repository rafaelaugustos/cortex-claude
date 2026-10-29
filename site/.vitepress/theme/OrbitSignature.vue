<script setup>
import { computed } from 'vue'
import { useData } from 'vitepress'

const labels = {
  'pt-BR': { before: 'Gerenciado pelo', after: '' },
  es: { before: 'Gestionado por', after: '' },
  'zh-CN': { before: '由', after: '托管' }
}
const { lang } = useData()
const label = computed(() => labels[lang.value] || { before: 'Managed by', after: '' })
</script>

<template>
  <div class="orbit-signature">
    <a class="orbit-signature-link" href="https://orbit.getcortexlabs.com/" target="_blank" rel="noopener noreferrer">
      <svg class="orbit-signature-symbol" width="20" height="20" viewBox="0 0 64 64" fill="none" aria-hidden="true">
        <circle cx="32" cy="32" r="13" stroke="currentColor" stroke-width="5" />
        <ellipse cx="32" cy="32" rx="27" ry="10" transform="rotate(-35 32 32)" stroke="currentColor" stroke-width="3" />
      </svg>
      <span>{{ label.before }} <strong>Orbit</strong><template v-if="label.after"> {{ label.after }}</template></span>
      <span class="orbit-signature-arrow" aria-hidden="true">↗</span>
    </a>
  </div>
</template>
