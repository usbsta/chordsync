from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str = "redis://localhost:6379"
    storage_path: str = "./storage"

    # Whisper model size: tiny | base | small | medium | large
    # larger = more accurate but slower
    whisper_model: str = "base"

    max_file_size_mb: int = 50

    # Sample rate used for all audio processing
    target_sample_rate: int = 22050

    class Config:
        env_file = ".env"


settings = Settings()
