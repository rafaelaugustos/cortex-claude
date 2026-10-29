<script setup>
defineProps({
  s: { type: String, required: true },
  p: { type: String, required: true },
  o: { type: String, required: true }
})
</script>

<template>
  <span class="fact">
    <span class="fact-node">{{ s }}</span>
    <span class="fact-edge" aria-hidden="true">→</span>
    <span class="fact-rel">{{ p }}</span>
    <span class="fact-edge" aria-hidden="true">→</span>
    <span class="fact-node">{{ o }}</span>
  </span>
</template>
