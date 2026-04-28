<template>
  <TransitionRoot as="template" :show="show">
    <Dialog as="div" class="relative z-50" @close="$emit('close')">
      <TransitionChild
        as="template"
        enter="ease-out duration-200"
        enter-from="opacity-0"
        enter-to="opacity-100"
        leave="ease-in duration-160"
        leave-from="opacity-100"
        leave-to="opacity-0"
      >
        <div class="fixed inset-0 bg-slate-950/45 backdrop-blur-sm" />
      </TransitionChild>

      <div class="fixed inset-0 z-10 overflow-y-auto">
        <div class="flex min-h-full items-center justify-center p-2 sm:p-4">
          <TransitionChild
            as="template"
            enter="ease-out duration-220"
            enter-from="opacity-0 translate-y-6 sm:scale-95"
            enter-to="opacity-100 translate-y-0 sm:scale-100"
            leave="ease-in duration-160"
            leave-from="opacity-100 translate-y-0 sm:scale-100"
            leave-to="opacity-0 translate-y-4 sm:scale-95"
          >
            <DialogPanel class="m3-reader-dialog md-dialog flex h-[calc(100vh-1rem)] w-[min(1400px,calc(100vw-1rem))] flex-col overflow-hidden text-left">
              <div class="m3-reader-dialog__head">
                <div class="min-w-0 flex-1">
                  <div class="m3-reader-dialog__chips">
                    <span v-for="chip in chips" :key="chip" class="m3-reader-chip">{{ chip }}</span>
                  </div>
                  <DialogTitle as="h3" class="m3-reader-title">
                    {{ title }}
                  </DialogTitle>
                  <p v-if="subtitle" class="m3-reader-subtitle">
                    {{ subtitle }}
                  </p>
                </div>

                <div class="m3-reader-dialog__actions">
                  <button type="button" class="md-icon-btn md-ripple" @click="$emit('close')" aria-label="关闭阅读层">
                    ×
                  </button>
                </div>
              </div>

              <div class="m3-reader-dialog__body">
                <article class="m3-reader-content">{{ content }}</article>
              </div>

              <div class="m3-reader-dialog__foot">
                <div class="m3-reader-dialog__foot-note">
                  <span v-if="confirmVersionIndex !== null && confirmVersionIndex !== undefined">
                    这是一版可直接确认的候选正文。
                  </span>
                  <span v-else>
                    这是完整内容预览，方便你先看清再决定下一步。
                  </span>
                </div>

                <div class="m3-reader-dialog__foot-actions">
                  <button type="button" class="md-btn md-btn-outlined md-ripple" @click="$emit('close')">
                    关闭
                  </button>
                  <button
                    v-if="confirmVersionIndex !== null && confirmVersionIndex !== undefined"
                    type="button"
                    class="md-btn md-btn-filled md-ripple disabled:opacity-50 disabled:cursor-not-allowed"
                    :disabled="confirmDisabled"
                    @click="$emit('confirm')"
                  >
                    {{ confirmLabel }}
                  </button>
                </div>
              </div>
            </DialogPanel>
          </TransitionChild>
        </div>
      </div>
    </Dialog>
  </TransitionRoot>
</template>

<script setup lang="ts">
import { Dialog, DialogPanel, DialogTitle, TransitionChild, TransitionRoot } from '@headlessui/vue'

interface Props {
  show: boolean
  title: string
  subtitle?: string
  content: string
  chips?: string[]
  confirmLabel?: string
  confirmVersionIndex?: number | null
  confirmDisabled?: boolean
}

withDefaults(defineProps<Props>(), {
  chips: () => [],
  confirmLabel: '确认这一版',
  confirmVersionIndex: null,
  confirmDisabled: false
})

defineEmits<{
  (e: 'close'): void
  (e: 'confirm'): void
}>()
</script>

<style scoped>
.m3-reader-dialog {
  border-radius: 28px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  box-shadow: 0 30px 80px rgba(15, 23, 42, 0.22);
  background:
    radial-gradient(circle at top right, rgba(37, 99, 235, 0.08), transparent 28%),
    radial-gradient(circle at bottom left, rgba(20, 184, 166, 0.08), transparent 24%),
    rgba(255, 255, 255, 0.98);
}

.m3-reader-dialog__head {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  justify-content: space-between;
  padding: 18px 20px 14px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.14);
}

.m3-reader-dialog__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.m3-reader-chip {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.06);
  color: #334155;
  font-size: 0.76rem;
  font-weight: 700;
}

.m3-reader-title {
  margin-top: 10px;
  font-size: clamp(1.15rem, 1.7vw, 1.7rem);
  font-weight: 800;
  line-height: 1.15;
  color: #0f172a;
}

.m3-reader-subtitle {
  margin-top: 8px;
  color: #475569;
  line-height: 1.7;
}

.m3-reader-dialog__body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 18px 20px 8px;
}

.m3-reader-content {
  max-width: 90ch;
  margin: 0 auto;
  white-space: pre-wrap;
  line-height: 2;
  color: #0f172a;
  font-size: 1.02rem;
}

.m3-reader-dialog__foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 14px 20px 18px;
  border-top: 1px solid rgba(148, 163, 184, 0.14);
  background: rgba(248, 250, 252, 0.96);
}

.m3-reader-dialog__foot-note {
  color: #64748b;
  font-size: 0.84rem;
}

.m3-reader-dialog__foot-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

@media (max-width: 768px) {
  .m3-reader-dialog {
    height: calc(100vh - 0.75rem);
    width: calc(100vw - 0.75rem);
    border-radius: 24px;
  }

  .m3-reader-dialog__head,
  .m3-reader-dialog__foot {
    padding-left: 16px;
    padding-right: 16px;
  }

  .m3-reader-content {
    font-size: 0.98rem;
  }
}
</style>
