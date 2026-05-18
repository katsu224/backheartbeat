from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    POSTGRES_DB: str = "heartbeat"
    POSTGRES_USER: str = "heartbeat_user"
    POSTGRES_PASSWORD: str = ""
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_DAYS: int = 90  # legacy — applies only to tokens issued before refresh-token rollout
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 90
    FIREBASE_CREDENTIALS_PATH: str = "/app/firebase-credentials.json"
    GIPHY_API_KEY: str = ""
    YOUTUBE_API_KEY: str = ""
    PUBLIC_BASE_URL: str = "https://api.laaf.lat"
    REDIS_URL: str = ""  # empty disables Redis pub/sub; required to run with multiple uvicorn workers

    model_config = {"env_file": ".env", "case_sensitive": False}


settings = Settings()
