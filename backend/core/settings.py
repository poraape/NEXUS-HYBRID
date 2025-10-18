import os
from pydantic import BaseModel

class _Settings(BaseModel):
    MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "200"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL","INFO")
    ENABLE_SPED_EXPORT: bool = os.getenv("ENABLE_SPED_EXPORT","true").lower()=="true"
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY","")
    DB_PATH: str = os.getenv("DB_PATH","./data/db.sqlite")

settings = _Settings()
