import os
from pathlib import Path
from typing import List
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

class _Settings(BaseModel):
    MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "200"))
    MAX_CONCURRENT_TASKS: int = int(os.getenv("MAX_CONCURRENT_TASKS", "8"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    ENABLE_SPED_EXPORT: bool = os.getenv("ENABLE_SPED_EXPORT", "true").lower() == "true"
    EXPORT_PROCESSING_LOG: bool = os.getenv("EXPORT_PROCESSING_LOG", "true").lower() == "true"
    OFFLINE_MODE: bool = os.getenv("OFFLINE_MODE", "false").lower() == "true"
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    DATA_PATH: Path = Field(default=Path(os.getenv("DATA_PATH", "./data")))
    LOG_DIR: Path = Field(default=Path(os.getenv("LOG_DIR", "./logs")))
    DB_PATH: Path = Field(default=Path(os.getenv("DB_PATH", "./data/learning.db")))
    ALLOWED_EXTENSIONS: List[str] = Field(
        default=[".zip", ".xml", ".csv", ".xlsx", ".pdf", ".png", ".jpg", ".jpeg"]
    )
    ALLOWED_MIME_PREFIXES: List[str] = Field(
        default=[
            "application/zip",
            "application/xml",
            "text/xml",
            "text/csv",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/pdf",
            "image/jpeg",
            "image/png",
        ]
    )

    @property
    def processing_log_file(self) -> Path:
        return self.LOG_DIR / "processing_log.json"

    def ensure_directories(self) -> None:
        self.DATA_PATH.mkdir(parents=True, exist_ok=True)
        self.LOG_DIR.mkdir(parents=True, exist_ok=True)
        if self.DB_PATH.parent != Path(""):
            self.DB_PATH.parent.mkdir(parents=True, exist_ok=True)

settings = _Settings()
settings.ensure_directories()
