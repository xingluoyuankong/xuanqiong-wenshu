"""Code-reviewed Agent capability provider catalog.

Environment configuration selects IDs from this catalog; it never supplies Python
module paths or callable names.
"""

from __future__ import annotations

from .provider_contract import ProviderManifest

PROJECT_READ_PROVIDER_PATH = "app.agent.providers.project_read:register_agent_tools"
MEMORY_READ_PROVIDER_PATH = "app.agent.providers.memory_read:register_agent_tools"
FORESHADOWING_READ_PROVIDER_PATH = "app.agent.providers.foreshadowing_read:register_agent_tools"
STRUCTURE_READ_PROVIDER_PATH = "app.agent.providers.structure_read:register_agent_tools"

BUILTIN_PROVIDER_IDS = frozenset({"project-read", "memory-read", "foreshadowing-read", "structure-read"})
PROVIDER_CATALOG: dict[str, str] = {
    "project-read": PROJECT_READ_PROVIDER_PATH,
    "memory-read": MEMORY_READ_PROVIDER_PATH,
    "foreshadowing-read": FORESHADOWING_READ_PROVIDER_PATH,
    "structure-read": STRUCTURE_READ_PROVIDER_PATH,
}
PROVIDER_MANIFESTS: dict[str, ProviderManifest] = {
    "project-read": ProviderManifest(
        provider_id="project-read",
        provider_version="1.0.0",
        capability_tags=("project-context", "outline", "research-summary", "statistics"),
        dependencies=("NovelService",),
    ),
    "memory-read": ProviderManifest(
        provider_id="memory-read",
        provider_version="1.0.0",
        capability_tags=("knowledge", "memory", "graph"),
        dependencies=("NovelService", "KnowledgeGraphService"),
    ),
    "foreshadowing-read": ProviderManifest(
        provider_id="foreshadowing-read",
        provider_version="1.0.0",
        capability_tags=("foreshadowing", "continuity", "tracking"),
        dependencies=("NovelService", "ForeshadowingService"),
    ),
    "structure-read": ProviderManifest(
        provider_id="structure-read",
        provider_version="1.0.0",
        capability_tags=("chapters", "versions", "diff"),
        dependencies=("NovelService",),
    ),
}
