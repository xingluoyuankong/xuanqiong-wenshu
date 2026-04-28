<template>
  <main class="reader-page">
    <section class="reader-shell">
      <header class="reader-topbar">
        <div class="reader-topbar__lead">
          <div class="reader-topbar__chips">
            <span class="reader-chip reader-chip--primary">全文阅读</span>
            <span v-for="chip in chips" :key="chip" class="reader-chip">{{ chip }}</span>
          </div>
          <div>
            <h1>{{ title || '正文阅读' }}</h1>
            <p>{{ subtitle || '当前章节完整正文' }}</p>
          </div>
        </div>

        <div class="reader-topbar__actions">
          <button type="button" class="reader-btn reader-btn--ghost" @click="goBack">返回写作台</button>
          <button type="button" class="reader-btn" @click="router.push('/')">返回主页</button>
        </div>
      </header>

      <section v-if="content" class="reader-body">
        <div class="reader-body__head">
          <div>
            <p class="reader-body__kicker">正文查看区</p>
            <h2>完整正文</h2>
            <p class="reader-body__desc">这里只做完整阅读，不改成文档/A4 风格，也不分栏。</p>
          </div>
          <div class="reader-body__meta">
            <span>全文字数 {{ content.length }}</span>
          </div>
        </div>

        <article class="reader-content">{{ content }}</article>
      </section>

      <div v-else class="reader-empty">没有读取到正文内容，请返回写作台重新打开。</div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

interface ReaderPayload {
  title?: string
  subtitle?: string
  content?: string
  chips?: string[]
}

const route = useRoute()
const router = useRouter()

const payload = computed<ReaderPayload>(() => {
  const key = typeof route.query.reader_key === 'string' ? route.query.reader_key : ''
  if (!key) return {}
  try {
    const raw = sessionStorage.getItem(key)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
})

const title = computed(() => payload.value.title || '')
const subtitle = computed(() => payload.value.subtitle || '')
const content = computed(() => payload.value.content || '')
const chips = computed(() => Array.isArray(payload.value.chips) ? payload.value.chips : [])

function goBack() {
  router.back()
}
</script>

<style scoped>
.reader-page {
  min-height: 100vh;
  padding: 10px 12px;
  color: #0f172a;
  background: linear-gradient(180deg, #edf4fb 0%, #f5f9fd 100%);
}

.reader-shell {
  max-width: 1180px;
  margin: 0 auto;
  display: grid;
  gap: 10px;
}

.reader-topbar,
.reader-body,
.reader-empty {
  border-radius: 24px;
  border: 1px solid rgba(148, 163, 184, 0.16);
}

.reader-topbar {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 10px;
  padding: 12px 14px;
  background:
    linear-gradient(135deg, rgba(219, 234, 254, 0.78), rgba(255, 255, 255, 0.94)),
    rgba(255, 255, 255, 0.92);
}

.reader-topbar__lead,
.reader-topbar__actions,
.reader-topbar__chips {
  display: flex;
  gap: 10px;
}

.reader-topbar__lead {
  min-width: 0;
  flex: 1;
  flex-direction: column;
}

.reader-topbar__lead h1 {
  margin: 0;
  font-size: 1.18rem;
  font-weight: 800;
  color: #0f172a;
}

.reader-topbar__lead p {
  margin: 4px 0 0;
  color: #475569;
  line-height: 1.45;
}

.reader-topbar__actions,
.reader-topbar__chips,
.reader-body__meta {
  flex-wrap: wrap;
  align-items: center;
}

.reader-chip {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.06);
  color: #334155;
  font-size: 0.78rem;
  font-weight: 700;
}

.reader-chip--primary {
  background: rgba(37, 99, 235, 0.12);
  color: #1d4ed8;
}

.reader-btn {
  min-height: 38px;
  padding: 0 14px;
  border: 1px solid #0f172a;
  border-radius: 999px;
  background: #0f172a;
  color: #fff;
  font-size: 0.84rem;
  font-weight: 800;
  cursor: pointer;
}

.reader-btn--ghost {
  border-color: rgba(148, 163, 184, 0.28);
  background: #fff;
  color: #334155;
}

.reader-body {
  display: grid;
  gap: 8px;
  padding: 12px 14px 14px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(244, 248, 254, 0.96)),
    rgba(250, 253, 255, 0.96);
  box-shadow: 0 6px 18px rgba(107, 155, 235, 0.08);
}

.reader-body__head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: flex-start;
  flex-wrap: wrap;
}

.reader-body__kicker {
  margin: 0 0 2px;
  font-size: 0.72rem;
  font-weight: 700;
  color: #2563eb;
  text-transform: uppercase;
  letter-spacing: 0.12em;
}

.reader-body__head h2 {
  margin: 0;
  font-size: 0.96rem;
  font-weight: 700;
  color: #0f172a;
}

.reader-body__desc {
  margin: 4px 0 0;
  color: #64748b;
  font-size: 0.82rem;
  line-height: 1.45;
}

.reader-body__meta span {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.05);
  color: #475569;
  font-size: 0.78rem;
  font-weight: 700;
}

.reader-content {
  white-space: pre-wrap;
  line-height: 1.5;
  font-size: 0.95rem;
  color: #111827;
  padding: 2px 1px 0;
}

.reader-empty {
  padding: 32px 16px;
  background: rgba(255, 255, 255, 0.92);
  color: #64748b;
  text-align: center;
}

@media (max-width: 768px) {
  .reader-page {
    padding: 8px;
  }

  .reader-topbar,
  .reader-body {
    padding: 12px;
  }

  .reader-topbar__actions {
    width: 100%;
  }

  .reader-btn {
    flex: 1;
  }
}
</style>
