from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from mot_analytics.web_api import router

app = FastAPI(title="MOT Analytics", docs_url=None, redoc_url=None)
app.include_router(router)
app.mount("/", StaticFiles(directory=Path(__file__).parent / "dist", html=True), name="frontend")
