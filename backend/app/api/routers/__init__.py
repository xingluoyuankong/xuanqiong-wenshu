# AIMETA P=路由聚合_注册所有子路由到主路由|R=路由注册|NR=不含具体端点实现|E=api_router|X=http|A=APIRouter聚合|D=fastapi|S=none|RD=./README.ai
from fastapi import APIRouter
from pydantic import BaseModel
from . import admin, llm_config, novels, optimizer, updates, writer, analytics, analytics_enhanced, foreshadowing, projects, review, outline, style, knowledge_graph, patch_diff, token_budget, clue_tracker, writing_skills

# emotion_curve.py 已明确下线，统一走 analytics.py 中的 /api/analytics/{project_id}/emotion-curve。

api_router = APIRouter()
api_router.include_router(novels.router)
api_router.include_router(writer.router)
api_router.include_router(admin.router)
api_router.include_router(updates.router)
api_router.include_router(llm_config.router)
api_router.include_router(optimizer.router)
api_router.include_router(analytics.router)
api_router.include_router(analytics_enhanced.router)
api_router.include_router(foreshadowing.router)
api_router.include_router(projects.router)
api_router.include_router(review.router)
# 新增：剧情演进路由
api_router.include_router(outline.router, prefix="/api/novels/{project_id}", tags=["outline-evolution"])
# 新增：风格学习RAG路由
api_router.include_router(style.router, prefix="/api/projects/{project_id}", tags=["style-rag"])
# 新增：知识图谱路由
api_router.include_router(knowledge_graph.router, prefix="/api/projects", tags=["knowledge-graph"])

# 新增：Patch+Diff 精细编辑路由
api_router.include_router(patch_diff.router, prefix="/api")

# 新增：Token 预算管理路由
api_router.include_router(token_budget.router, prefix="/api")

# 新增：线索追踪路由
api_router.include_router(clue_tracker.router, prefix="/api")

# 新增：写作技能路由
api_router.include_router(writing_skills.router, prefix="/api")


