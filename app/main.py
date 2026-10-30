"""FastAPI app: outside portal, mock eID, SMS inbox, audit page, bot task. Portal owner: SWE 2.

Outside flow (each step audited):
  GET  /r/{t}             link opened -> neutral page, "Mit ID Austria anmelden"
  GET  /eid/authorize     mock IdP: pick a test citizen
  POST /eid/authorize     -> redirect /r/{t}/callback?assertion=…
  GET  /r/{t}/callback    identity checked: eID name must match the expected person, else blocked
  GET  /r/{t}/answer      patient + request revealed (need-to-know), answer form
  POST /r/{t}/answer      answer sent -> intake_service (file / review / reject) -> receipt
"""
from __future__ import annotations

import asyncio
import contextlib
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import bot, db, dashboard
from app.clinic_router import router as clinic_router
from app.portal_router import router as portal_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    task = asyncio.create_task(bot.start())
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


app = FastAPI(title="BefundBrücke", lifespan=lifespan)

app.include_router(portal_router)

if not os.environ.get("PORTAL_ONLY", ""):
    app.include_router(clinic_router)
    app.include_router(dashboard.router)
