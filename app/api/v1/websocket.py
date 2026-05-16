import uuid

import structlog
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_token
from app.db.session import get_db
from app.repositories.couple_repo import CoupleRepository
from app.services.connection_manager import manager

logger = structlog.get_logger()
router = APIRouter(tags=["websocket"])


async def _get_partner_id(db: AsyncSession, user_id: uuid.UUID) -> uuid.UUID | None:
    couple = await CoupleRepository(db).get_by_user_id(user_id)
    if not couple:
        return None
    return couple.user_b_id if couple.user_a_id == user_id else couple.user_a_id


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    verified_id = verify_token(token)
    if not verified_id:
        await websocket.close(code=4001)
        return

    try:
        parsed_id = uuid.UUID(user_id)
    except ValueError:
        await websocket.close(code=4001)
        return

    if verified_id != parsed_id:
        await websocket.close(code=4001)
        return

    await websocket.accept()
    await manager.connect(parsed_id, websocket)

    partner_id = await _get_partner_id(db, parsed_id)
    if partner_id:
        await manager.send_to_user(partner_id, {"type": "partner_online"})

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
            elif msg_type in ("watch_sync", "watch_invite", "watch_clip"):
                to_user = data.get("to")
                if to_user:
                    try:
                        target_id = uuid.UUID(to_user)
                        data["from"] = str(parsed_id)
                        await manager.send_to_user(target_id, data)
                    except ValueError:
                        pass
            else:
                await websocket.send_json(
                    {"type": "error", "message": f"Unknown type: {msg_type}"}
                )
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error("ws_error", user_id=user_id, error=str(exc))
    finally:
        manager.disconnect(parsed_id)
        if partner_id:
            await manager.send_to_user(partner_id, {"type": "partner_offline"})
