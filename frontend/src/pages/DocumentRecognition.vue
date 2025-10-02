<script setup lang="ts">
import LeftMenu from '@/components/LeftMenu.vue';
import Content from '@/components/Content.vue';

</script>

<template>
  <div class="main">
    <div class="left-menu">
      <LeftMenu />
    </div>
    <div class="content">
      <Content />
    </div>
  </div>
</template>

<style scoped lang="scss">
.main {
  display: flex;
  flex-flow: row nowrap;
  gap: 20px;
  & .left-menu {
    flex: 1;
  }
  & .content {
    flex: 3;
  }
}
</style>
