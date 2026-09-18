import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface Notification {
  id: number
  type: 'success' | 'error' | 'info' | 'warning'
  message: string
  duration?: number
}

export const useNotificationStore = defineStore('notification', () => {
  const notifications = ref<Notification[]>([])
  let nextId = 1

  const notify = (type: Notification['type'], message: string, duration = 4000) => {
    const id = nextId++
    notifications.value.push({ id, type, message, duration })
    if (duration > 0) {
      setTimeout(() => remove(id), duration)
    }
  }

  const remove = (id: number) => {
    const idx = notifications.value.findIndex((n) => n.id === id)
    if (idx !== -1) notifications.value.splice(idx, 1)
  }

  const success = (msg: string) => notify('success', msg)
  const error = (msg: string) => notify('error', msg)
  const info = (msg: string) => notify('info', msg)
  const warning = (msg: string) => notify('warning', msg)

  return { notifications, notify, remove, success, error, info, warning }
})
