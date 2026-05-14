from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    POSTGRES_DB: str = "heartbeat"
    POSTGRES_USER: str = "heartbeat_user"
    POSTGRES_PASSWORD: str = ""
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_DAYS: int = 90
    FIREBASE_CREDENTIALS_PATH: str = "/app/firebase-credentials.json"
    GIPHY_API_KEY: str = ""
    YOUTUBE_API_KEY: str = ""

    model_config = {"env_file": ".env", "case_sensitive": False}


settings = Settings()
