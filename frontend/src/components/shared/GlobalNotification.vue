<template>
  <Teleport to="body">
    <div class="notification-container" role="region" aria-label="通知">
      <TransitionGroup name="toast">
        <div
          v-for="n in notifications"
          :key="n.id"
          class="toast"
          :class="`toast--${n.type}`"
          role="alert"
          @click="remove(n.id)"
        >
          <span class="toast-icon">
            <!-- success -->
            <svg v-if="n.type === 'success'" class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"/>
            </svg>
            <!-- error -->
            <svg v-else-if="n.type === 'error'" class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"/>
            </svg>
            <!-- warning -->
            <svg v-else-if="n.type === 'warning'" class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"/>
            </svg>
            <!-- info -->
            <svg v-else class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z"/>
            </svg>
          </span>
          <span class="toast-message">{{ n.message }}</span>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { useNotificationStore } from '@/stores/notification'
import { storeToRefs } from 'pinia'

const store = useNotificationStore()
const { notifications } = storeToRefs(store)
const { remove } = store
</script>

<style scoped>
.notification-container {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 8px;
  pointer-events: none;
}

.toast {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border-radius: 12px;
  background: var(--md-surface-container-high, #f5f9fc);
  color: var(--md-on-surface, #0f172a);
  font-size: 14px;
  box-shadow:
    0 4px 12px rgba(15, 23, 42, 0.12),
    0 1px 3px rgba(15, 23, 42, 0.08);
  cursor: pointer;
  pointer-events: auto;
  max-width: 340px;
  min-width: 220px;
  line-height: 1.5;
}

.toast--success {
  border-left: 3px solid var(--md-success, #22c55e);
}
.toast--error {
  border-left: 3px solid var(--md-error, #ef4444);
}
.toast--warning {
  border-left: 3px solid var(--md-warning, #f59e0b);
}
.toast--info {
  border-left: 3px solid var(--md-primary, #7eb8e8);
}

.toast-icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
}
.toast--success .toast-icon  { color: var(--md-success, #22c55e); }
.toast--error .toast-icon    { color: var(--md-error, #ef4444); }
.toast--warning .toast-icon  { color: var(--md-warning, #f59e0b); }
.toast--info .toast-icon     { color: var(--md-primary, #7eb8e8); }

.toast-message {
  flex: 1;
  min-width: 0;
  word-break: break-word;
}

.toast-enter-active,
.toast-leave-active {
  transition: all 0.28s cubic-bezier(0.4, 0, 0.2, 1);
}
.toast-enter-from {
  opacity: 0;
  transform: translateX(48px);
}
.toast-leave-to {
  opacity: 0;
  transform: translateX(48px);
}
.toast-move {
  transition: transform 0.28s cubic-bezier(0.4, 0, 0.2, 1);
}
</style>
