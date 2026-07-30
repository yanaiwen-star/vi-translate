"""Chat-history sessions + messages for the mini program.

These are stored in the same database as the web console, so a user's history
survives across devices and is tied to their (possibly merged) account. All
endpoints require authentication; the mini program is always logged in after
``/api/wx/login``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.jwt import require_user_id
from app.db import get_db
from app.models import Message, Session

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class SessionIn(BaseModel):
    title: str = ""


class MessageIn(BaseModel):
    sourceLang: str = ""
    sourceText: str = ""
    targetLang: str = ""
    targetText: str = ""
    audioDuration: int = 0


@router.post("")
def create_session(
    body: SessionIn,
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> dict:
    s = Session(user_id=user_id, title=(body.title or "新会话").strip()[:200])
    db.add(s)
    db.commit()
    db.refresh(s)
    return {"sessionId": s.id}


@router.get("")
def list_sessions(
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
    limit: int = 50,
) -> dict:
    rows = (
        db.query(Session)
        .filter(Session.user_id == user_id)
        .order_by(Session.updated_at.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return {
        "list": [
            {
                "id": s.id,
                "title": s.title,
                "previewText": s.preview_text,
                "messageCount": s.message_count or 0,
                "updatedAt": s.updated_at.isoformat() if s.updated_at else "",
            }
            for s in rows
        ]
    }


@router.get("/{session_id}")
def get_session(
    session_id: str,
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> dict:
    s = (
        db.query(Session)
        .filter(Session.id == session_id, Session.user_id == user_id)
        .first()
    )
    if not s:
        raise HTTPException(status_code=404, detail="会话不存在。")
    msgs = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
        .all()
    )
    return {
        "list": [
            {
                "id": m.id,
                "sourceLang": m.source_lang,
                "targetLang": m.target_lang,
                "sourceText": m.source_text,
                "targetText": m.target_text,
                "createdAt": m.created_at.isoformat() if m.created_at else "",
            }
            for m in msgs
        ]
    }


@router.post("/{session_id}/messages")
def add_message(
    session_id: str,
    body: MessageIn,
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> dict:
    s = (
        db.query(Session)
        .filter(Session.id == session_id, Session.user_id == user_id)
        .first()
    )
    if not s:
        raise HTTPException(status_code=404, detail="会话不存在。")
    m = Message(
        session_id=session_id,
        source_lang=body.sourceLang,
        source_text=body.sourceText,
        target_lang=body.targetLang,
        target_text=body.targetText,
        audio_duration=body.audioDuration or 0,
    )
    db.add(m)
    s.message_count = (s.message_count or 0) + 1
    if body.sourceText:
        s.preview_text = body.sourceText[:200]
    db.commit()
    db.refresh(m)
    return {
        "id": m.id,
        "sourceLang": m.source_lang,
        "targetLang": m.target_lang,
        "sourceText": m.source_text,
        "targetText": m.target_text,
        "createdAt": m.created_at.isoformat() if m.created_at else "",
    }


@router.delete("/{session_id}")
def delete_session(
    session_id: str,
    user_id: str = Depends(require_user_id),
    db: Session = Depends(get_db),
) -> dict:
    s = (
        db.query(Session)
        .filter(Session.id == session_id, Session.user_id == user_id)
        .first()
    )
    if not s:
        raise HTTPException(status_code=404, detail="会话不存在。")
    db.query(Message).filter(Message.session_id == session_id).delete()
    db.delete(s)
    db.commit()
    return {"deleted": True}
