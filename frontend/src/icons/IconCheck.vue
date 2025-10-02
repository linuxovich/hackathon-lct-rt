<script setup>
const colorDefault = '#ffffff';
const sizeDefault = 20;
const { color = colorDefault, size = sizeDefault } = defineProps({
  color: String,
  size: Number,
});
</script>

<template>
  <svg
    :style="{ scale: size / sizeDefault }"
    width="20"
    height="20"
    viewBox="0 0 20 20"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
  >
    <path
      d="M7.43431 15.7643L2.2343 10.5344C1.9219 10.2202 1.9219 9.71077 2.2343 9.39654L3.36565 8.25865C3.67806 7.94442 4.18462 7.94442 4.49703 8.25865L8 11.7817L15.503 4.23565C15.8154 3.92145 16.3219 3.92145 16.6344 4.23565L17.7657 5.37353C18.0781 5.68774 18.0781 6.19718 17.7657 6.51141L8.56569 15.7644C8.25325 16.0786 7.74672 16.0786 7.43431 15.7643Z"
      :fill="color"
    />
  </svg>
</template>
