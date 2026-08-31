import { describe, expect, it } from 'vitest'

import { componentDtsTarget } from './componentDtsTarget'

describe('componentDtsTarget', () => {
  it('只允许开发服务器更新已跟踪的组件声明，生产构建不得写文件', () => {
    expect(componentDtsTarget('serve')).toBe('src/components.d.ts')
    expect(componentDtsTarget('build')).toBe(false)
  })
})
