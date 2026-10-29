"""Matrix bot (matrix-nio): relays Dr. Hofer's commands to commands.handle and drains the outbox. Owner: SWE 1.

With MATRIX_ENABLED=0 only the console printer runs, so everything else works without Synapse.
"""
from __future__ import annotations

import asyncio
import logging

from app import commands, engine_client, notify
from app.config import settings

log = logging.getLogger("befundbruecke.bot")


async def console_printer() -> None:
    while True:
        for m in notify.pending():
            print(f"[MATRIX → {settings.doctor_mxid}] {m['text']}", flush=True)
            notify.mark_sent(m["id"])
        await asyncio.sleep(1)


async def run_bot() -> None:
    from nio import AsyncClient, MatrixRoom, RoomMessageAudio, RoomMessageText

    client = AsyncClient(settings.matrix_homeserver, settings.matrix_bot_user)
    resp = await client.login(settings.matrix_bot_password)
    log.info("matrix login: %s", resp)
    await client.join(settings.matrix_room_id)
    first = await client.sync(timeout=3000, full_state=True)   # skip history: only react to new messages
    since = first.next_batch

    async def say(text: str) -> None:
        await client.room_send(settings.matrix_room_id, "m.room.message", {"msgtype": "m.text", "body": text})

    async def on_message(room: MatrixRoom, event: RoomMessageText) -> None:
        if room.room_id != settings.matrix_room_id or event.sender == settings.matrix_bot_user:
            return
        if not event.body.startswith("!") and event.sender != settings.doctor_mxid:
            return           # a plain sentence is a request only when the doctor writes it
        # TODO(SWE 1): only accept commands from members of the clinic directory (here: DOCTOR_MXID)
        reply = await asyncio.to_thread(commands.handle, event.body, event.sender)
        await say(reply)

    async def on_voice(room: MatrixRoom, event: RoomMessageAudio) -> None:
        """Element voice message -> engine (speech-to-text + request job). The audio is kept in memory only."""
        if room.room_id != settings.matrix_room_id or event.sender != settings.doctor_mxid:
            return
        resp = await client.download(event.url)
        audio = getattr(resp, "body", None)
        if not audio:
            await say("Sprachnachricht konnte nicht geladen werden.")
            return
        res = await asyncio.to_thread(engine_client.request_audio, audio, getattr(resp, "filename", None) or "voice.ogg")
        del audio
        await say(await asyncio.to_thread(commands.from_engine, res, event.sender, "voice"))

    client.add_event_callback(on_message, RoomMessageText)
    client.add_event_callback(on_voice, RoomMessageAudio)

    async def drain() -> None:
        while True:
            for m in notify.pending():
                await say(m["text"])
                notify.mark_sent(m["id"])
            await asyncio.sleep(1)

    asyncio.create_task(drain())
    await client.sync_forever(timeout=30000, since=since)


async def start() -> None:
    if settings.matrix_enabled:
        await run_bot()
    else:
        await console_printer()
