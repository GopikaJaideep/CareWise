"""Chat API — primary entry point that drives the orchestrator."""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.base import AgentName, SessionContext
from app.agents.orchestrator import Orchestrator
from app.api.schemas import (
    AgentTrace, ChatRequest, ChatResponse, ConversationOut, ConversationSummary, MessageOut,
)
from app.core.auth import get_current_user
from app.core.database import get_db, get_session_factory
from app.core.safety import redact_pii, validate_response
from app.core.streaming import ReplySink, open_sink
from app.core.tracing import start_trace
from app.services import demo, memory
from app.models.db import BurnoutCheckin, Conversation, Message, User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    return await run_chat_turn(payload, current_user, db)


# Chat turns still running after their stream's client went away; kept so they finish and save.
_background_turns: set[asyncio.Task] = set()


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/stream")
async def chat_stream(
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
    sessions=Depends(get_session_factory),
) -> StreamingResponse:
    """The same chat turn as POST /api/chat, sent as server-sent events while it's written.

    Events: "delta" {text} (a preview, released sentence by sentence after the safety filter),
    "blocked" (the filter stopped the preview), then "done" (the final ChatResponse, which the app
    shows and which is saved) or "error" {status, detail}. If the client disconnects, the turn
    still finishes and is saved.
    """
    user_id = current_user.id
    sink = ReplySink()

    async def turn() -> ChatResponse:
        open_sink(sink)  # only this task's context: other requests are unaffected
        try:
            # Its own session: a streaming response outlives request-scoped dependencies.
            async with sessions() as db:
                user = await db.get(User, user_id)
                return await run_chat_turn(payload, user, db)
        finally:
            sink.queue.put_nowait(None)

    task = asyncio.create_task(turn())
    _background_turns.add(task)
    task.add_done_callback(_background_turns.discard)

    async def events():
        while (item := await sink.queue.get()) is not None:
            kind, text = item
            yield _sse(kind, {"text": text} if kind == "delta" else {"reason": text})
        try:
            result = await task
        except HTTPException as e:
            yield _sse("error", {"status": e.status_code, "detail": e.detail})
            return
        except Exception:
            logger.exception("Streamed chat turn failed")
            yield _sse("error", {"status": 500, "detail": "Something went wrong writing a reply."})
            return
        yield _sse("done", result.model_dump(mode="json"))

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        # No caching, and no proxy buffering (nginx honours X-Accel-Buffering), or nothing streams.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def run_chat_turn(payload: ChatRequest, current_user: User, db: AsyncSession) -> ChatResponse:
    """One chat turn: save the message, run the agents, filter and save the reply."""
    if current_user.is_demo and await demo.demo_messages_used(db, current_user.id) >= demo.DEMO_MESSAGE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"This demo has reached its {demo.DEMO_MESSAGE_LIMIT}-message limit. "
                   "Create a free account to keep going.",
        )
    # Get or create conversation
    if payload.conversation_id:
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == payload.conversation_id,
                Conversation.user_id == current_user.id,
            )
        )
        conversation = result.scalar_one_or_none()
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        conversation = Conversation(
            user_id=current_user.id,
            title=payload.message[:60] + ("…" if len(payload.message) > 60 else ""),
        )
        db.add(conversation)
        await db.flush()

    # Persist user message
    user_msg = Message(
        conversation_id=conversation.id,
        role="user",
        content=payload.message,
    )
    db.add(user_msg)
    await db.flush()

    # Build session context
    history_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(10)
    )
    history_msgs = list(reversed(list(history_result.scalars())))[:-1]  # exclude the just-added one
    history = [{"role": m.role, "content": m.content} for m in history_msgs]
    # Which agent replied last, so a short answer to its question ("yes", "6 hours, stress 7")
    # goes back to it instead of being classified on its own.
    last_agent = next((m.agent_used for m in reversed(history_msgs) if m.role == "assistant"), None)

    # Pull latest burnout score for emotional support context
    bc_result = await db.execute(
        select(BurnoutCheckin)
        .where(BurnoutCheckin.user_id == current_user.id)
        .order_by(BurnoutCheckin.created_at.desc())
        .limit(1)
    )
    latest_bc = bc_result.scalar_one_or_none()

    ctx = SessionContext(
        user_id=current_user.id,
        conversation_id=conversation.id,
        user_message=payload.message,
        user_profile={
            "display_name": current_user.display_name,
            "care_recipient_name": current_user.care_recipient_name,
            "care_recipient_relation": current_user.care_recipient_relation,
            "diagnosis_context": current_user.diagnosis_context,
            # Facts remembered from earlier chats, only if the person turned memory on.
            "memories": [m.text for m in await memory.load_memories(db, current_user.id)]
            if current_user.memory_enabled else [],
        },
        history=history,
        metadata={
            "recent_burnout_score": latest_bc.burnout_score if latest_bc else None,
            "timezone": payload.timezone,
            "last_agent": last_agent,
        },
    )

    # Run orchestration, tracing routing, agents and every model call for this turn.
    with start_trace() as trace:
        if ctx.user_profile["memories"]:
            trace.extra["memories_used"] = len(ctx.user_profile["memories"])
        orchestrator = Orchestrator(db)
        responses = await orchestrator.run(ctx)
        final_text = orchestrator.synthesize(responses)

        # Final output validation
        valid, reason = validate_response(final_text)
        if not valid:
            trace.extra["output_filter"] = reason
            final_text = (
                "I started to write a response but caught something that might cross into specific medical advice. "
                f"Could you ask your treatment team about this directly? (Filter triggered: {reason})"
            )
    turn = trace.summary()
    # One structured line per turn for the server logs. No message text, and no retrieved article
    # names either: "nausea#0" next to a user id is health information. The full trace (visible
    # only to the user) is stored with the reply; the log gets the count.
    log_turn = {**turn}
    if "retrieval" in log_turn:
        log_turn["retrieval"] = {"mode": turn["retrieval"]["mode"], "sections": len(turn["retrieval"]["sections"])}
    logger.info("chat_turn %s", json.dumps({"user_id": current_user.id, "conversation_id": conversation.id, **log_turn}))

    # Persist assistant message
    last_response = responses[-1] if responses else None
    assistant_msg = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=final_text,
        agent_used=last_response.agent.value if last_response else None,
        risk_level=last_response.metadata.get("risk_level") if last_response else None,
        meta={
            "agents": [r.agent.value for r in responses],
            "trace": [{"agent": r.agent.value, "metadata": r.metadata} for r in responses],
            "turn": turn,
        },
    )
    db.add(assistant_msg)
    await db.commit()
    await db.refresh(assistant_msg)

    # Update what CareWise remembers, in the background (never delays the reply; skipped for
    # turns that reached the safety response, and when memory is off).
    memory.after_turn(current_user, conversation.id, any(r.agent == AgentName.SAFETY for r in responses))

    return ChatResponse(
        conversation_id=conversation.id,
        message_id=assistant_msg.id,
        content=final_text,
        agent_trace=[
            AgentTrace(agent=r.agent.value, metadata=r.metadata) for r in responses
        ],
        risk_level=assistant_msg.risk_level,
        turn=turn,
    )


@router.get("/conversations", response_model=list[ConversationSummary])
async def list_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Conversation]:
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == current_user.id)
        .order_by(Conversation.created_at.desc(), Conversation.id.desc())
    )
    return list(result.scalars())


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Conversation:
    # Eager-load messages (ordered by the relationship): lazy-loading, or
    # assigning to the relationship, raises MissingGreenlet in an async session.
    result = await db.execute(
        select(Conversation)
        .where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
        .options(selectinload(Conversation.messages))
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv
