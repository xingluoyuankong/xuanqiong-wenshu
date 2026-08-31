"""Application service for immutable Agent conversation summaries over message ranges."""
from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import select

from ..models.agent import AgentMessage, AgentRun, AgentSession
from ..models.agent_conversation import ConversationSummary
from .agent_context_service import canonical_digest


class AgentConversationIntegrityError(ValueError):
    """Raised when a summary does not match its session, run, message range, or digest."""


def conversation_source_material(messages: list[AgentMessage]) -> list[dict[str, Any]]:
    return [
        {"sequence": message.sequence, "role": message.role, "content": message.content}
        for message in messages
    ]


def conversation_summary_material(summary: ConversationSummary) -> dict[str, Any]:
    return {
        "summary_id": summary.summary_id,
        "session_id": summary.session_id,
        "run_id": summary.run_id,
        "user_id": summary.user_id,
        "project_id": summary.project_id,
        "correlation_id": summary.correlation_id,
        "transaction_id": summary.transaction_id,
        "summary_kind": summary.summary_kind,
        "summarizer_id": summary.summarizer_id,
        "start_message_sequence": summary.start_message_sequence,
        "end_message_sequence": summary.end_message_sequence,
        "message_count": summary.message_count,
        "source_digest": summary.source_digest,
        "summary_text": summary.summary_text,
        "summary_json": summary.summary_json,
    }


class AgentConversationService:
    """Creates and verifies append-only summaries over contiguous persisted messages."""

    def __init__(self, session: Any):
        self.session = session

    async def create_summary(
        self,
        *,
        session: AgentSession,
        start_message_sequence: int,
        end_message_sequence: int,
        summary_text: str,
        summary_json: dict[str, Any] | None = None,
        run: AgentRun | None = None,
        summary_kind: str = "rolling",
        summarizer_id: str | None = None,
    ) -> ConversationSummary:
        if run is not None and (run.session_id != session.id or run.user_id != session.user_id):
            raise AgentConversationIntegrityError("run and session association do not match")
        if start_message_sequence < 1 or end_message_sequence < start_message_sequence:
            raise AgentConversationIntegrityError("message range is invalid")
        if not isinstance(summary_json or {}, dict):
            raise AgentConversationIntegrityError("summary_json must be a JSON object")
        text = str(summary_text).strip()
        if not text:
            raise AgentConversationIntegrityError("summary_text must not be blank")
        messages = await self._messages_in_range(session.id, start_message_sequence, end_message_sequence)
        expected_sequences = list(range(start_message_sequence, end_message_sequence + 1))
        if [message.sequence for message in messages] != expected_sequences:
            raise AgentConversationIntegrityError("summary message range must be contiguous and fully persisted")
        source_digest = canonical_digest(conversation_source_material(messages))
        summary = ConversationSummary(
            summary_id=str(uuid4()),
            session_id=session.id,
            run_id=run.id if run is not None else None,
            user_id=session.user_id,
            project_id=run.project_id if run is not None else session.project_id,
            correlation_id=run.correlation_id if run is not None else None,
            transaction_id=run.transaction_id if run is not None else None,
            summary_kind=str(summary_kind).strip() or "rolling",
            summarizer_id=(str(summarizer_id).strip() or None) if summarizer_id is not None else None,
            start_message_sequence=start_message_sequence,
            end_message_sequence=end_message_sequence,
            message_count=len(messages),
            source_digest=source_digest,
            summary_text=text,
            summary_json=summary_json or {},
            digest="",
        )
        summary.digest = canonical_digest(conversation_summary_material(summary))
        self.session.add(summary)
        await self.session.flush()
        await self.verify_summary(summary, verify_source=True)
        return summary

    async def ensure_visible_response_summary(
        self,
        *,
        run_id: str,
        user_id: int,
        final_message_sequence: int,
    ) -> ConversationSummary:
        """Idempotently archive one persisted visible assistant response.

        The summary is deliberately deterministic: persisting a final response must
        not require another provider call.  Each response covers only messages that
        are not already covered by an older session summary, and recovery can call
        this method again without creating a second fact for the same Run/message.
        """
        run = (
            await self.session.execute(
                select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == user_id)
            )
        ).scalar_one_or_none()
        if run is None:
            raise AgentConversationIntegrityError("run does not exist for user")
        conversation = (
            await self.session.execute(
                select(AgentSession).where(
                    AgentSession.id == run.session_id,
                    AgentSession.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if conversation is None:
            raise AgentConversationIntegrityError("run session does not exist for user")
        final_message = (
            await self.session.execute(
                select(AgentMessage).where(
                    AgentMessage.session_id == conversation.id,
                    AgentMessage.user_id == user_id,
                    AgentMessage.sequence == int(final_message_sequence),
                )
            )
        ).scalar_one_or_none()
        if final_message is None or final_message.role != "assistant":
            raise AgentConversationIntegrityError("final visible response message is not persisted")

        existing = await self.get_visible_response_summary(
            run_id=run.id,
            user_id=user_id,
            final_message_sequence=final_message.sequence,
            verify_source=True,
        )
        if existing is not None:
            return existing

        previous = (
            await self.session.execute(
                select(ConversationSummary)
                .where(
                    ConversationSummary.session_id == conversation.id,
                    ConversationSummary.end_message_sequence < final_message.sequence,
                )
                .order_by(ConversationSummary.end_message_sequence.desc(), ConversationSummary.created_at.desc())
                .limit(1)
            )
        ).scalars().first()
        start_sequence = int(previous.end_message_sequence) + 1 if previous is not None else 1
        excerpt = " ".join(final_message.content.strip().split())[:1200]
        message_count = final_message.sequence - start_sequence + 1
        summary_text = (
            f"已归档本段会话消息 #{start_sequence}-#{final_message.sequence}，"
            f"共 {message_count} 条；最终助手回复：{excerpt}"
        )
        return await self.create_summary(
            session=conversation,
            run=run,
            start_message_sequence=start_sequence,
            end_message_sequence=final_message.sequence,
            summary_text=summary_text,
            summary_json={
                "mode": "deterministic_visible_response",
                "final_message_sequence": final_message.sequence,
                "final_message_character_count": len(final_message.content),
                "final_message_excerpt": excerpt,
            },
            summary_kind="visible_response",
            summarizer_id="runtime:visible-response",
        )

    async def get_visible_response_summary(
        self,
        *,
        run_id: str,
        user_id: int,
        final_message_sequence: int | None = None,
        verify_source: bool = False,
    ) -> ConversationSummary | None:
        """Read the durable visible-response summary used by response recovery."""
        statement = select(ConversationSummary).where(
            ConversationSummary.run_id == run_id,
            ConversationSummary.user_id == user_id,
            ConversationSummary.summary_kind == "visible_response",
        )
        if final_message_sequence is not None:
            statement = statement.where(
                ConversationSummary.end_message_sequence == int(final_message_sequence)
            )
        statement = statement.order_by(
            ConversationSummary.end_message_sequence.desc(),
            ConversationSummary.created_at.desc(),
        )
        summary = (await self.session.execute(statement.limit(1))).scalars().first()
        if summary is not None and verify_source:
            await self.verify_summary(summary, verify_source=True)
        return summary

    async def _messages_in_range(self, session_id: str, start: int, end: int) -> list[AgentMessage]:
        return list((await self.session.execute(
            select(AgentMessage)
            .where(
                AgentMessage.session_id == session_id,
                AgentMessage.sequence >= start,
                AgentMessage.sequence <= end,
            )
            .order_by(AgentMessage.sequence)
        )).scalars())

    async def get_summary(self, summary_id: str) -> ConversationSummary | None:
        return (await self.session.execute(
            select(ConversationSummary).where(ConversationSummary.summary_id == summary_id)
        )).scalar_one_or_none()

    async def list_summaries_for_run(
        self,
        *,
        run_id: str,
        session_id: str,
        user_id: int,
        limit: int = 100,
    ) -> list[ConversationSummary]:
        """List only summaries explicitly attributed to one verified Run."""
        bounded_limit = min(max(int(limit), 1), 500)
        statement = (
            select(ConversationSummary)
            .where(
                ConversationSummary.run_id == run_id,
                ConversationSummary.session_id == session_id,
                ConversationSummary.user_id == user_id,
            )
            .order_by(
                ConversationSummary.start_message_sequence.asc(),
                ConversationSummary.end_message_sequence.asc(),
                ConversationSummary.created_at.asc(),
                ConversationSummary.id.asc(),
            )
            .limit(bounded_limit)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def verify_summary(self, summary: ConversationSummary, *, verify_source: bool = False) -> None:
        expected = canonical_digest(conversation_summary_material(summary))
        if summary.digest != expected:
            raise AgentConversationIntegrityError("conversation summary digest mismatch")
        if summary.end_message_sequence < summary.start_message_sequence:
            raise AgentConversationIntegrityError("conversation summary range is invalid")
        if summary.message_count != summary.end_message_sequence - summary.start_message_sequence + 1:
            raise AgentConversationIntegrityError("conversation summary message_count does not match its range")
        if verify_source:
            messages = await self._messages_in_range(
                summary.session_id, summary.start_message_sequence, summary.end_message_sequence
            )
            if len(messages) != summary.message_count:
                raise AgentConversationIntegrityError("conversation summary source range is no longer contiguous")
            if canonical_digest(conversation_source_material(messages)) != summary.source_digest:
                raise AgentConversationIntegrityError("conversation summary source digest mismatch")
