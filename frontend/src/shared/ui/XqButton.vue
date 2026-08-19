<template>
  <button
    class="xq-button xq-focus-ring"
    :class="[`xq-button--${variant}`, `xq-button--${size}`, { 'is-loading': loading }]"
    :disabled="disabled || loading"
    type="button"
  >
    <span v-if="$slots.icon || loading" class="xq-button__icon" aria-hidden="true">
      <span v-if="loading" class="xq-button__spinner" />
      <slot v-else name="icon" />
    </span>
    <span class="xq-button__label"><slot /></span>
  </button>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'outline' | 'text'
    size?: 'sm' | 'md' | 'lg'
    loading?: boolean
    disabled?: boolean
  }>(),
  {
    variant: 'primary',
    size: 'md',
    loading: false,
    disabled: false,
  },
)
</script>

<style scoped>
.xq-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.55rem;
  border: 1px solid transparent;
  border-radius: var(--xq-radius-pill);
  font-family: var(--xq-font-sans);
  font-weight: 700;
  letter-spacing: 0.03em;
  cursor: pointer;
  transition:
    transform var(--xq-fast),
    box-shadow var(--xq-fast),
    background var(--xq-fast),
    border-color var(--xq-fast);
}

.xq-button:hover:not(:disabled) {
  transform: translateY(-1px);
}

.xq-button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.xq-button--sm {
  min-height: 2.25rem;
  padding: 0 0.9rem;
  font-size: 0.84rem;
}

.xq-button--md {
  min-height: 2.75rem;
  padding: 0 1.2rem;
  font-size: 0.94rem;
}

.xq-button--lg {
  min-height: 3.25rem;
  padding: 0 1.55rem;
  font-size: 1rem;
}

.xq-button--primary {
  color: #ffffff;
  background: linear-gradient(135deg, #2563eb, #0891b2);
  box-shadow: 0 12px 28px rgba(37, 99, 235, 0.22);
}

.xq-button--secondary {
  color: var(--xq-ink);
  background: rgba(255, 255, 255, 0.82);
  border-color: var(--xq-border);
  box-shadow: var(--xq-shadow-paper);
}

.xq-button--ghost {
  color: #2563eb;
  background: transparent;
  border-color: rgba(37, 99, 235, 0.22);
}

.xq-button--danger {
  color: #ffffff;
  background: linear-gradient(135deg, #8f2f2b, var(--xq-cinnabar));
  box-shadow: 0 12px 28px rgba(185, 74, 61, 0.2);
}

.xq-button__spinner {
  width: 1em;
  height: 1em;
  border: 2px solid currentColor;
  border-right-color: transparent;
  border-radius: 50%;
  animation: xq-spin 700ms linear infinite;
}

@keyframes xq-spin {
  to {
    transform: rotate(360deg);
  }
}

.xq-button--outline {
  color: #2563eb;
  background: transparent;
  border-color: #2563eb;
}
.xq-button--outline:hover:not(:disabled) {
  background: rgba(37, 99, 235, 0.06);
}
.xq-button--text {
  color: #475569;
  background: transparent;
  border-color: transparent;
  padding-left: 0.5rem;
  padding-right: 0.5rem;
}
.xq-button--text:hover:not(:disabled) {
  background: rgba(148, 163, 184, 0.08);
  color: #0f172a;
}

</style>
