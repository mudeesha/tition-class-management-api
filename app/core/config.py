from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    test_database_url: str | None = None

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    refresh_token_days: int = 14

    cors_origins: list[str] = ["http://localhost:3000"]

    # "Today" for class days, fees and door scans. Customers are in Sri Lanka.
    timezone: str = "Asia/Colombo"

    # Uploaded files (tute PDFs). Can move to cloud storage later behind app/core/storage.py.
    storage_dir: str = "storage"
    max_upload_mb: int = 20


settings = Settings()
