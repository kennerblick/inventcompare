import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import scheduler
from app.routers import comparison, health, settings, sources

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="InventCompare API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(sources.router)
app.include_router(comparison.router)
app.include_router(settings.router)


@app.on_event("startup")
async def on_startup():
    scheduler.start()


@app.on_event("shutdown")
async def on_shutdown():
    scheduler.stop()
