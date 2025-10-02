<script setup lang="ts">
const { color = '#000000' } = defineProps<{ color?: string }>();
</script>

<template>
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M11 3L6 8L11 13" :stroke="color" stroke-width="2" stroke-linecap="round" />
  </svg>
</template>

<style scoped lang="scss"></style>
