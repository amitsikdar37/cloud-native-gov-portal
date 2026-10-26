"""
Quick-start script — run the API server directly with `python run.py`
"""

import uvicorn
from app.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,           # Auto-reload on code changes (dev only)
        log_level="info",
    )
