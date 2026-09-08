"""Portable deterministic command ordering using persisted request-event sequence."""
from sqlalchemy import func, select
from ..models.agent import AgentEventRecord, AgentRunCommand


def command_request_sequence():
    # Event/command are committed together. Scope all identity dimensions so a
    # legacy or corrupt lookalike event cannot reorder a different command.
    return (select(func.min(AgentEventRecord.sequence)).where(
        AgentEventRecord.run_id == AgentRunCommand.run_id,
        AgentEventRecord.user_id == AgentRunCommand.user_id,
        AgentEventRecord.correlation_id == AgentRunCommand.correlation_id,
        AgentEventRecord.transaction_id.is_not_distinct_from(AgentRunCommand.transaction_id),
        AgentEventRecord.event_type == 'run_command_requested',
        AgentEventRecord.data_json['command_id'].as_string() == AgentRunCommand.id,
        AgentEventRecord.data_json['command_type'].as_string() == AgentRunCommand.command_type,
    ).correlate(AgentRunCommand).scalar_subquery())


def command_order_by():
    # Sequence is Run-local, not a global clock. Group only timestamp ties by
    # Run; legacy commands without a matching request event retain ID fallback.
    return (AgentRunCommand.requested_at.asc(), AgentRunCommand.run_id.asc(),
            func.coalesce(command_request_sequence(), 2147483647).asc(),
            AgentRunCommand.id.asc())
