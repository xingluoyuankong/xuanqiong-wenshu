import { createApp, h } from 'vue'
import AgentWorkspaceShell from '../src/features/agent/AgentWorkspaceShell.vue'
createApp({
  render: () => h(AgentWorkspaceShell, { projectTitle: 'UI006 焦点验收项目' }, {
    sidebar: () => h('label', ['项目检索', h('input', { 'aria-label': '项目检索', 'data-testid': 'focus-sidebar-input' })]),
    main: () => h('label', ['创作目标', h('textarea', { 'aria-label': '创作目标', 'data-testid': 'focus-main-input' })]),
    activity: () => h('button', { 'data-testid': 'focus-activity-button' }, '查看运行详情'),
  }),
}).mount('#app')
