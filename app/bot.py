"""Matrix bot (matrix-nio): relays Dr. Hofer's commands to commands.handle, keeps one card per request up to
date with a one-line ping only where she has to look (app/status_message.py), turns reactions ("Senden",
"Ablegen", "Verwerfen") into commands (app/reactions.py) and drains the outbox. Owner: SWE 1.

With MATRIX_ENABLED=0 only the console printer runs, so everything else works without Synapse.
"""
from __future__ import annotations

import asyncio
import io
import logging

from app import chat_icons, commands, db, engine_client, matrix_format, notify, reactions, status_message
from app.config import settings

log = logging.getLogger("befundbruecke.bot")


async def upload_chat_images(client) -> None:
    """Draw the chat icons and bridge images once and upload them; from then on the bot's HTML shows them instead of
    emoji and dots (app/matrix_format.py). If an upload fails, messages keep their plain text."""
    async def up(data: bytes, name: str) -> str | None:
        resp, _ = await client.upload(io.BytesIO(data), content_type="image/png", filename=name, filesize=len(data))
        return getattr(resp, "content_uri", None)
    try:
        icons = {n: await up(chat_icons.icon(n), f"{n}.png") for n in chat_icons.ICON_NAMES}
        bridges = {(k, t): await up(chat_icons.bridge(k, t), f"bridge-{k}-{t}.png")
                   for k in range(6) for t in chat_icons.TONES}
    except Exception:
        log.exception("chat images not uploaded")
        return
    if all(icons.values()) and all(bridges.values()):
        matrix_format.BRIDGES.update(bridges)
        matrix_format.ICONS.update(icons)


async def console_printer() -> None:
    while True:
        for m in notify.pending():
            print(f"[MATRIX → {settings.doctor_mxid}] {m['text']}", flush=True)
            notify.mark_sent(m["id"])
        await asyncio.sleep(1)


async def run_bot() -> None:
    from nio import AsyncClient, MatrixRoom, ReactionEvent, RoomMessageAudio, RoomMessageText

    client = AsyncClient(settings.matrix_homeserver, settings.matrix_bot_user)
    resp = await client.login(settings.matrix_bot_password)
    log.info("matrix login: %s", resp)
    await client.join(settings.matrix_room_id)
    if settings.chat_images:
        await upload_chat_images(client)
    first = await client.sync(timeout=3000, full_state=True)   # skip history: only react to new messages
    since = first.next_batch
    started = db.now()

    async def send(content: dict) -> str | None:
        resp = await client.room_send(settings.matrix_room_id, "m.room.message", content)
        if not getattr(resp, "event_id", None):
            log.warning("matrix send failed: %s", resp)
        return getattr(resp, "event_id", None)

    async def say(text: str, buttons: dict[str, str] | None = None, reply_to: str | None = None) -> str | None:
        event_id = await send(matrix_format.content(text, reply_to))
        if not event_id:
            return None
        keys = reactions.offer(event_id, buttons) if buttons is not None else reactions.register(event_id, text)
        for key in keys:                                   # word pills under the message, tapped like a button
            await client.room_send(settings.matrix_room_id, "m.reaction",
                                   {"m.relates_to": {"rel_type": "m.annotation", "event_id": event_id, "key": key}})
        return event_id

    async def answer(command: str, reply: str) -> None:
        if rid := status_message.drafted(reply):        # the draft becomes the request's card
            text = await asyncio.to_thread(status_message.card_text, rid, reply)
            if event_id := await say(text, {reactions.SENDEN: f"!senden {rid}"}):
                status_message.saved(rid, event_id, text)
        elif status_message.is_ack(command, reply):      # acks are not posted: the card shows the change
            reactions.spend(command)                      # typed or tapped: its buttons are used up either way
            for event_id, text in await asyncio.to_thread(status_message.decided, command):
                await send(matrix_format.edit(event_id, text))   # the 🔍 ping shows the outcome where she tapped
        else:
            await say(reply)

    async def on_message(room: MatrixRoom, event: RoomMessageText) -> None:
        if room.room_id != settings.matrix_room_id or event.sender == settings.matrix_bot_user:
            return
        if not event.body.startswith("!") and event.sender not in settings.authorized_senders:
            return           # a plain sentence is a request only from the clinic directory; others are chat
        # commands.handle refuses senders outside AUTHORIZED_SENDERS (the clinic directory)
        reply = await asyncio.to_thread(commands.handle, event.body, event.sender)
        await answer(event.body, reply)

    async def on_reaction(room: MatrixRoom, event: ReactionEvent) -> None:
        if room.room_id != settings.matrix_room_id or event.sender == settings.matrix_bot_user:
            return
        if done := await asyncio.to_thread(reactions.handle, event.reacts_to, event.key, event.sender):
            await answer(*done)

    async def on_voice(room: MatrixRoom, event: RoomMessageAudio) -> None:
        """Element voice message -> engine (speech-to-text + request job). The audio is kept in memory only."""
        if room.room_id != settings.matrix_room_id or event.sender not in settings.authorized_senders:
            return
        resp = await client.download(event.url)
        audio = getattr(resp, "body", None)
        if not audio:
            await say("Sprachnachricht nicht verarbeitet\nDie Audiodatei konnte nicht geladen werden. Bitte erneut senden.")
            return
        res = await asyncio.to_thread(engine_client.request_audio, audio, getattr(resp, "filename", None) or "voice.ogg")
        del audio
        await answer("", await asyncio.to_thread(commands.from_engine, res, event.sender, "voice"))

    client.add_event_callback(on_message, RoomMessageText)
    client.add_event_callback(on_reaction, ReactionEvent)
    client.add_event_callback(on_voice, RoomMessageAudio)

    async def drain() -> None:
        while True:
            for m in notify.pending():
                if not status_message.replaced(m["text"], m["request_id"]):   # the card and its pings say it
                    await say(m["text"])
                notify.mark_sent(m["id"])
            # one card per request, edited in place; then a one-line ping where Dr. Hofer has to look
            for event_id, request_id, text in await asyncio.to_thread(status_message.updates, started):
                sent_id = await send(matrix_format.edit(event_id, text) if event_id else matrix_format.content(text))
                if sent_id:
                    status_message.saved(request_id, event_id or sent_id, text)
            for request_id, text, buttons, seq in await asyncio.to_thread(status_message.pings):
                if await say(text, buttons):            # a short line of its own, no quoted card above it
                    status_message.pinged(request_id, seq)
            await asyncio.sleep(1)

    asyncio.create_task(drain())
    await client.sync_forever(timeout=30000, since=since)


async def start() -> None:
    if settings.matrix_enabled:
        await run_bot()
    else:
        await console_printer()
