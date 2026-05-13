import uuid

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.security import verify_token
from app.services.connection_manager import manager

logger = structlog.get_logger()
router = APIRouter(tags=["websocket"])


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str,
    token: str = Query(...),
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

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
            else:
                await websocket.send_json(
                    {"type": "error", "message": f"Unknown type: {msg_type}"}
                )
    except WebSocketDisconnect:
        manager.disconnect(parsed_id)
    except Exception as exc:
        logger.error("ws_error", user_id=user_id, error=str(exc))
        manager.disconnect(parsed_id)
