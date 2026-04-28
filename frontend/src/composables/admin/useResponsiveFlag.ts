import { onBeforeUnmount, onMounted, ref } from 'vue'

export const useResponsiveFlag = (maxWidth: number) => {
  const matched = ref(false)

  const update = () => {
    matched.value = window.innerWidth < maxWidth
  }

  onMounted(() => {
    update()
    window.addEventListener('resize', update)
  })

  onBeforeUnmount(() => {
    window.removeEventListener('resize', update)
  })

  return {
    matched,
    update,
  }
}
