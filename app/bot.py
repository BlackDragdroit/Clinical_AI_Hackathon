"""Matrix bot (matrix-nio): relays Dr. Hofer's commands to commands.handle, drains the outbox, keeps one
status message per request up to date (app/status_message.py) and turns ✅/❌ reactions into commands
(app/reactions.py). Owner: SWE 1.

With MATRIX_ENABLED=0 only the console printer runs, so everything else works without Synapse.
"""
from __future__ import annotations

import asyncio
import logging

from app import commands, db, matrix_format, notify, reactions, status_message
from app.config import settings

log = logging.getLogger("befundbruecke.bot")


async def console_printer() -> None:
    while True:
        for m in notify.pending():
            print(f"[MATRIX → {settings.doctor_mxid}] {m['text']}", flush=True)
            notify.mark_sent(m["id"])
        await asyncio.sleep(1)


async def run_bot() -> None:
    from nio import AsyncClient, MatrixRoom, ReactionEvent, RoomMessageText

    client = AsyncClient(settings.matrix_homeserver, settings.matrix_bot_user)
    resp = await client.login(settings.matrix_bot_password)
    log.info("matrix login: %s", resp)
    await client.join(settings.matrix_room_id)
    first = await client.sync(timeout=3000, full_state=True)   # skip history: only react to new messages
    since = first.next_batch
    started = db.now()

    async def send(content: dict) -> str | None:
        resp = await client.room_send(settings.matrix_room_id, "m.room.message", content)
        if not getattr(resp, "event_id", None):
            log.warning("matrix send failed: %s", resp)
        return getattr(resp, "event_id", None)

    async def say(text: str) -> None:
        event_id = await send(matrix_format.content(text))
        if not event_id:
            return
        for key in reactions.register(event_id, text):     # ✅ / ❌ under the message, tapped like a button
            await client.room_send(settings.matrix_room_id, "m.reaction",
                                   {"m.relates_to": {"rel_type": "m.annotation", "event_id": event_id, "key": key}})

    async def on_message(room: MatrixRoom, event: RoomMessageText) -> None:
        if room.room_id != settings.matrix_room_id or event.sender == settings.matrix_bot_user:
            return
        if not event.body.startswith("!"):
            return
        # commands.handle refuses senders outside AUTHORIZED_SENDERS (the clinic directory)
        reply = await asyncio.to_thread(commands.handle, event.body, event.sender)
        await say(reply)

    async def on_reaction(room: MatrixRoom, event: ReactionEvent) -> None:
        if room.room_id != settings.matrix_room_id or event.sender == settings.matrix_bot_user:
            return
        reply = await asyncio.to_thread(reactions.handle, event.reacts_to, event.key, event.sender)
        if reply:
            await say(reply)

    client.add_event_callback(on_message, RoomMessageText)
    client.add_event_callback(on_reaction, ReactionEvent)

    async def drain() -> None:
        while True:
            for m in notify.pending():
                await say(m["text"])
                notify.mark_sent(m["id"])
            # one status message per request: posted once it is sent, then edited in place
            for event_id, request_id, text in await asyncio.to_thread(status_message.updates, started):
                sent_id = await send(matrix_format.edit(event_id, text) if event_id else matrix_format.content(text))
                if sent_id:
                    status_message.saved(request_id, event_id or sent_id, text)
            await asyncio.sleep(1)

    asyncio.create_task(drain())
    await client.sync_forever(timeout=30000, since=since)


async def start() -> None:
    if settings.matrix_enabled:
        await run_bot()
    else:
        await console_printer()
