import uuid

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.controllers import ChatController
from app.models import User
from app.routers.deps import chat_controller, get_session, require_student
from app.schemas import AskIn, MessageOut, SessionCreate, SessionOut

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/library")
async def library(user: User = Depends(require_student), ctrl: ChatController = Depends(chat_controller)):
    """Books available for the student's grade, grouped by subject."""
    return await ctrl.library(user)


@router.get("/usage")
async def my_usage(user: User = Depends(require_student), ctrl: ChatController = Depends(chat_controller)):
    return await ctrl.usage(user)


@router.post("/sessions", response_model=SessionOut, status_code=201)
async def create_session(body: SessionCreate, user: User = Depends(require_student),
                         ctrl: ChatController = Depends(chat_controller)):
    return await ctrl.create_session(user, body)


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(user: User = Depends(require_student), ctrl: ChatController = Depends(chat_controller)):
    return await ctrl.list_sessions(user)


@router.get("/sessions/{sid}/messages", response_model=list[MessageOut])
async def messages(sid: uuid.UUID, limit: int = 200, user: User = Depends(require_student),
                   ctrl: ChatController = Depends(chat_controller)):
    return await ctrl.messages(user, sid, limit)


@router.delete("/sessions/{sid}", status_code=204)
async def delete_session(sid: uuid.UUID, user: User = Depends(require_student),
                         ctrl: ChatController = Depends(chat_controller)):
    await ctrl.delete_session(user, sid)
    return Response(status_code=204)


@router.post("/sessions/{sid}/ask")
async def ask(sid: uuid.UUID, body: AskIn, user: User = Depends(require_student),
              ctrl: ChatController = Depends(chat_controller), session: AsyncSession = Depends(get_session)):
    events = await ctrl.start(user, sid, body)
    await session.close()  # release the DB connection: the answer may stream for a while
    if body.stream:
        return StreamingResponse(ctrl.as_sse(events), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    return await ctrl.as_json(events)
