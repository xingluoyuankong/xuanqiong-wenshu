import { describe, expect, it } from 'vitest'
import { globalAlert } from './useAlert'

describe('useAlert', () => {
  it('使用中文默认标题和按钮文案', async () => {
    const before = globalAlert.alerts.value.length
    void globalAlert.showConfirm('确认继续？')
    const alert = globalAlert.alerts.value[globalAlert.alerts.value.length - 1]

    expect(alert.title).toBe('请确认')
    expect(alert.confirmText).toBe('确定')
    expect(alert.cancelText).toBe('取消')
    expect(alert.showCancel).toBe(true)

    globalAlert.closeAlert(alert.id, false)
    expect(globalAlert.alerts.value.length).toBe(before)
  })

  it('成功、错误、提示弹窗默认标题可读', () => {
    const successPromise = globalAlert.showSuccess('保存成功')
    const success = globalAlert.alerts.value[globalAlert.alerts.value.length - 1]
    expect(success.title).toBe('成功')
    globalAlert.closeAlert(success.id, false)
    void successPromise

    const errorPromise = globalAlert.showError('保存失败')
    const error = globalAlert.alerts.value[globalAlert.alerts.value.length - 1]
    expect(error.title).toBe('错误')
    globalAlert.closeAlert(error.id, false)
    void errorPromise

    const infoPromise = globalAlert.showInfo('请稍候')
    const info = globalAlert.alerts.value[globalAlert.alerts.value.length - 1]
    expect(info.title).toBe('提示')
    globalAlert.closeAlert(info.id, false)
    void infoPromise
  })
})
