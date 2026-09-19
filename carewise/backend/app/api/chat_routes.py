"""Chat API — primary entry point that drives the orchestrator."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import SessionContext
from app.agents.orchestrator import Orchestrator
from app.api.schemas import (
    AgentTrace, ChatRequest, ChatResponse, ConversationOut, MessageOut,
)
from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.safety import redact_pii, validate_response
from app.models.db import BurnoutCheckin, Conversation, Message, User

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
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
        },
        history=history,
        metadata={
            "recent_burnout_score": latest_bc.burnout_score if latest_bc else None,
            "timezone": payload.timezone,
        },
    )

    # Run orchestration
    orchestrator = Orchestrator(db)
    responses = await orchestrator.run(ctx)
    final_text = orchestrator.synthesize(responses)

    # Final output validation
    valid, reason = validate_response(final_text)
    if not valid:
        final_text = (
            "I started to write a response but caught something that might cross into specific medical advice. "
            f"Could you ask your treatment team about this directly? (Filter triggered: {reason})"
        )

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
        },
    )
    db.add(assistant_msg)
    await db.commit()
    await db.refresh(assistant_msg)

    return ChatResponse(
        conversation_id=conversation.id,
        message_id=assistant_msg.id,
        content=final_text,
        agent_trace=[
            AgentTrace(agent=r.agent.value, metadata=r.metadata) for r in responses
        ],
        risk_level=assistant_msg.risk_level,
    )


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Conversation]:
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == current_user.id)
        .order_by(Conversation.created_at.desc())
    )
    return list(result.scalars())


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Conversation:
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msg_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.created_at.asc())
    )
    conv.messages = list(msg_result.scalars())
    return conv
