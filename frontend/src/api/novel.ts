// AIMETA P=小说API客户端_小说和章节接口|R=小说CRUD_章节管理_生成|NR=不含UI逻辑|E=api:novel|X=internal|A=novelApi对象|D=axios|S=net|RD=./README.ai
// Phase 5.2 重构：此文件现为 re-export 桥接文件
// 类型定义已提取到 @/api/types/novel
// API 客户端代码已提取到 @/api/novel-client
// 所有从 @/api/novel 导入的代码无需修改，此文件 re-export 全部内容

// re-export 所有类型定义
export * from '@/api/types/novel'

// re-export API 客户端类和错误处理
export { ApiError, NovelAPI, OptimizerAPI, AnalyticsAPI, TokenBudgetAPI } from '@/api/novel-client'
