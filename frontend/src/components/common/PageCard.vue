<template>
  <div class="card bg-base-100 shadow-xl">
    <div
      v-if="title || $slots['header-right']"
      class="card-header flex justify-between items-center p-4 border-b border-base-300"
    >
      <h2 class="card-title">
        {{ title }}
      </h2>
      <slot name="header-right" />
    </div>
    <div
      class="card-body"
      :style="bodyStyle"
    >
      <slot />
    </div>
  </div>
</template>

<script>
export default {
  name: 'PageCard',
  props: {
    title: {
      type: String,
      default: '',
    },
    bodyStyle: {
      type: Object,
      default: () => ({}),
    },
  },
};
</script>

<style scoped>
.card {
  margin-bottom: 1.25rem;
}
</style>
