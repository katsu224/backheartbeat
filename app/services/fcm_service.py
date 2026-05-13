from datetime import datetime, timezone

import structlog

from app.core.config import settings

logger = structlog.get_logger()

_initialized = False


def init_firebase() -> None:
    global _initialized
    if _initialized:
        return
    try:
        import firebase_admin
        from firebase_admin import credentials

        cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
        firebase_admin.initialize_app(cred)
        _initialized = True
        logger.info("firebase_initialized")
    except FileNotFoundError:
        logger.warning(
            "firebase_credentials_not_found",
            path=settings.FIREBASE_CREDENTIALS_PATH,
            note="FCM disabled — place firebase-credentials.json to enable",
        )
    except Exception as exc:
        logger.error("firebase_init_failed", error=str(exc))


async def send_fcm_notification(
    fcm_token: str,
    from_name: str,
    button_label: str = "",
    video_url: str = "",
    bg_color: str = "",
    duration_seconds: int = 0,
) -> bool:
    if not _initialized:
        logger.warning("fcm_not_initialized")
        return False
    try:
        from firebase_admin import messaging

        message = messaging.Message(
            android=messaging.AndroidConfig(priority="high"),
            data={
                "type": "incoming_trigger",
                "from_name": from_name,
                "button_label": button_label,
                "video_url": video_url,
                "bg_color": bg_color,
                "duration_seconds": str(duration_seconds),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            token=fcm_token,
        )
        response = messaging.send(message)
        logger.info("fcm_sent", message_id=response, token_prefix=fcm_token[:20])
        return True
    except Exception as exc:
        logger.error("fcm_send_failed", error=str(exc), token_prefix=fcm_token[:20])
        return False
