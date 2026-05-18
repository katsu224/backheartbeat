import asyncio
import uuid

import structlog
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_token
from app.db.session import get_db
from app.repositories.couple_repo import CoupleRepository
from app.services.connection_manager import PRESENCE_TTL_SECONDS, manager

logger = structlog.get_logger()
router = APIRouter(tags=["websocket"])


PRESENCE_HEARTBEAT_INTERVAL = max(15, PRESENCE_TTL_SECONDS // 2)


async def _presence_heartbeat(user_id: uuid.UUID) -> None:
    try:
        while True:
            await asyncio.sleep(PRESENCE_HEARTBEAT_INTERVAL)
            await manager.refresh_presence(user_id)
    except asyncio.CancelledError:
        pass


async def _get_partner_id(db: AsyncSession, user_id: uuid.UUID) -> uuid.UUID | None:
    couple = await CoupleRepository(db).get_by_user_id(user_id)
    if not couple:
        return None
    return couple.user_b_id if couple.user_a_id == user_id else couple.user_a_id


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    auth_header = websocket.headers.get("authorization", "")
    token = auth_header[7:] if auth_header.lower().startswith("bearer ") else ""
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
    heartbeat_task = asyncio.create_task(_presence_heartbeat(parsed_id))

    partner_id = await _get_partner_id(db, parsed_id)
    if partner_id:
        # Tell the partner we just came online.
        await manager.send_to_user(partner_id, {"type": "partner_online"})
        # And tell ourselves whether the partner is already online — covers
        # the race where the partner connected first and their inbound
        # "partner_online" hit no one.
        if await manager.is_connected(partner_id):
            try:
                await websocket.send_json({"type": "partner_online"})
            except Exception as exc:
                logger.warning("ws_initial_state_failed", user_id=user_id, error=str(exc))

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
            elif msg_type in ("watch_sync", "watch_invite", "watch_clip", "watch_chat", "webrtc_signal"):
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
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        manager.disconnect(parsed_id)
        if partner_id:
            await manager.send_to_user(partner_id, {"type": "partner_offline"})
