<script setup lang="ts">
import { useRouter } from 'vue-router';

const router = useRouter();

// onMounted(() => {
//   router.push('/tasks');
// });
</script>

<template>
  <!-- <HeaderMenu /> -->
  <div class="content">
    <RouterView />
  </div>
</template>

<style scoped lang="scss">
.content {
  margin: 0 auto 0 auto;
  padding: 20px;
  // max-width: 1200px;
}
</style>
