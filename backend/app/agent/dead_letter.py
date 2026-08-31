"""Dead-letter projection for Agent jobs.

The durable source remains AgentJob.status=dead_letter. This module only
normalizes safe operator-facing data; it does not silently replay jobs.
"""
from __future__ import annotations

from typing import Any

from ..models.agent import AgentJob


def project_dead_letter(job: AgentJob) -> dict[str, Any]:
    if job.status != "dead_letter":
        raise ValueError("job is not dead-lettered")
    return {
        "job_id": job.id,
        "run_id": job.run_id,
        "user_id": job.user_id,
        "project_id": job.project_id,
        "kind": job.kind,
        "status": job.status,
        "attempt_count": job.attempt_count,
        "max_attempts": job.max_attempts,
        "error_type": job.error_type,
        "error_detail": job.error_detail,
        "created_at": job.created_at,
        "finished_at": job.finished_at,
    }
