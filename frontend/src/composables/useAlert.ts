import { ref } from 'vue'

type AlertType = 'success' | 'error' | 'info' | 'confirmation'

interface Alert {
  id: number
  visible: boolean
  type: AlertType
  title: string
  message: string
  showCancel: boolean
  confirmText: string
  cancelText: string
  onConfirm: (result: boolean) => void
}

const alerts = ref<Alert[]>([])
let alertId = 0

const closeAlert = (id: number, result: boolean) => {
  const index = alerts.value.findIndex((alert) => alert.id === id)
  if (index !== -1) {
    alerts.value[index].onConfirm(result)
    alerts.value.splice(index, 1)
  }
}

const defaultTitle = (type: AlertType) => {
  if (type === 'success') return '成功'
  if (type === 'error') return '错误'
  if (type === 'confirmation') return '请确认'
  return '提示'
}

const showAlert = (
  message: string,
  type: AlertType = 'info',
  title = '',
  options: Partial<Omit<Alert, 'id' | 'visible' | 'message' | 'type' | 'title'>> = {},
) => {
  return new Promise<boolean>((resolve) => {
    const id = alertId++
    const newAlert: Alert = {
      id,
      visible: true,
      type,
      title: title || defaultTitle(type),
      message,
      showCancel: options.showCancel || false,
      confirmText: options.confirmText || '确定',
      cancelText: options.cancelText || '取消',
      onConfirm: resolve,
    }
    alerts.value.push(newAlert)

    if ((type === 'success' || type === 'info') && !newAlert.showCancel) {
      setTimeout(() => closeAlert(id, false), 3000)
    }
  })
}

const showSuccess = (message: string, title = '成功') => showAlert(message, 'success', title)
const showError = (message: string, title = '错误') => showAlert(message, 'error', title)
const showInfo = (message: string, title = '提示') => showAlert(message, 'info', title)
const showConfirm = (message: string, title = '请确认') => showAlert(message, 'confirmation', title, { showCancel: true })

export const globalAlert = {
  alerts,
  showAlert,
  closeAlert,
  showSuccess,
  showError,
  showInfo,
  showConfirm,
}

export function useAlert() {
  return {
    showAlert: globalAlert.showAlert,
  }
}
