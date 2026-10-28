"""Log vào chat/kênh đã chọn; cấu hình inline qua Helper Bot, không ghi nội dung chat."""

import asyncio
import re
import secrets
import time
from collections import OrderedDict
from html import escape

from i18n import get_text
from shell_commands import clipped_html, config_secrets, redact


LOG_TYPES = {"afk", "error", "update", "profile", "command"}
AFK_FIELDS = {"chat", "sender", "reason", "duration", "status"}
CONFIG_KEYS = ("LOG_CHAT_ID", "LOG_TYPES", "LOG_AFK_FIELDS")
LABELS = {
    "vi": {"afk": "AFK + link 🔒", "error": "Lỗi", "update": "Cập nhật code", "profile": "Tên / bio", "command": "Lệnh (không tham số)", "chat": "Chat", "sender": "Người gửi", "reason": "Lý do", "duration": "Thời gian AFK", "status": "Trạng thái", "action": "Tác vụ", "name": "Tên", "bio": "Bio"},
    "en": {"afk": "AFK + link 🔒", "error": "Errors", "update": "Code updates", "profile": "Name / bio", "command": "Commands (no arguments)", "chat": "Chat", "sender": "Sender", "reason": "Reason", "duration": "AFK time", "status": "Status", "action": "Action", "name": "Name", "bio": "Bio"},
}


def selections(config):
    kinds = set(re.split(r"[,\s]+", config.get("LOG_TYPES", "") or "afk,error,update")) & LOG_TYPES
    kinds.add("afk")
    raw = config.get("LOG_AFK_FIELDS", "")
    fields = set(re.split(r"[,\s]+", raw)) & AFK_FIELDS if raw else set(AFK_FIELDS)
    return kinds, fields


def message_link(event):
    chat_id = getattr(event, "chat_id", None)
    message_id = getattr(event, "id", None) or getattr(getattr(event, "message", None), "id", None)
    if not isinstance(chat_id, int) or isinstance(chat_id, bool) or not isinstance(message_id, int) or isinstance(message_id, bool) or message_id <= 0 or not chat_id:
        return None
    if chat_id <= -1000000000000:
        return f"https://t.me/c/{-chat_id - 1000000000000}/{message_id}"
    key = "user_id" if chat_id > 0 else "chat_id"
    return f"tg://openmessage?{key}={abs(chat_id)}&message_id={message_id}"


class ChatLogger:
    def __init__(self, interval=1):
        self.client = None
        self.controls = None
        self.control_username = ""
        self.config = lambda: {}
        self.queue = asyncio.Queue(maxsize=100)
        self.worker = None
        self.interval = interval
        self.cards = OrderedDict()
        self.dropped = 0
        self.last_error = ""
        self.last_warning = float("-inf")
        self.peer = None
        self.peer_target = None

    def bind(self, client, config):
        if self.client is not client:
            self.peer = self.peer_target = None
        self.client, self.config = client, config

    def bind_controls(self, client, config, username=""):
        self.controls, self.config = client, config
        self.control_username = username or ""

    def target(self):
        try:
            return int(self.config().get("LOG_CHAT_ID", "") or 0)
        except (ValueError, TypeError):
            return 0

    async def destination(self, target):
        if self.peer_target == target and self.peer is not None:
            return self.peer
        if not callable(getattr(self.client, "get_input_entity", None)):
            return target
        try:
            peer = await self.client.get_input_entity(target)
        except ValueError:
            # StringSession không giữ entity cache sau restart. Tìm lại đúng
            # dialog đã lưu, không lưu access_hash/session vào cấu hình log.
            peer = None
            async for dialog in self.client.iter_dialogs():
                if dialog.id == target:
                    peer = dialog.input_entity
                    break
            if peer is None:
                raise ValueError("Log destination is not accessible") from None
        self.peer_target, self.peer = target, peer
        return peer

    async def send(self, target, text):
        peer = await self.destination(target)
        await self.client.send_message(peer, text, parse_mode="html", link_preview=False, silent=True)

    def emit(self, kind, details, *, link=None):
        config = self.config()
        kinds, fields = selections(config)
        target = self.target()
        if self.client is None or not target or kind not in kinds or (kind == "afk" and not link):
            return False
        lang = "en" if config.get("LANGUAGE") == "en" else "vi"
        values = [str(value) for value in [*config_secrets(config), config.get("API_ID", "")] if value]
        values += [escape(value) for value in values if isinstance(value, str)]
        text = get_text(f"log_event_{kind}", lang)
        for key, value in details.items():
            if kind == "afk" and key not in fields:
                continue
            if key not in LABELS[lang] or not isinstance(value, (str, int, float)):
                continue
            clean = clipped_html(redact(str(value), values), 250)[0]
            text += f"\n<b>{LABELS[lang][key]}:</b> {clean}"
        if link:
            text += f'\n🔗 <a href="{escape(link, quote=True)}">{get_text("log_original", lang)}</a>'
            if link.startswith("tg://openmessage?"):
                text += f"\n<code>{escape(link)}</code>\n<i>{get_text('log_private_note', lang)}</i>"
        if self.queue.full():
            self.dropped += 1
            if kind != "afk":
                return False
            self.queue.get_nowait()
            self.queue.task_done()
        self.queue.put_nowait((target, kind, text, self.signature(config)))
        if self.worker is None or self.worker.done():
            self.worker = asyncio.create_task(self._drain())
        return True

    def discard_pending(self):
        while not self.queue.empty():
            self.queue.get_nowait()
            self.queue.task_done()

    async def _drain(self):
        while not self.queue.empty():
            target, kind, text, signature = self.queue.get_nowait()
            try:
                if self.client is not None and self.target() == target and signature == self.signature(self.config()) and kind in selections(self.config())[0]:
                    await asyncio.wait_for(self.send(target, text), timeout=15)
                    self.last_error = ""
            except Exception as exc:
                self.last_error = type(exc).__name__
                if time.monotonic() - self.last_warning >= 60:
                    print(f"[ℹ️] Chưa gửi được log ({self.last_error}); kiểm tra quyền gửi tin ở chat log.")
                    self.last_warning = time.monotonic()
            finally:
                self.queue.task_done()
            if not self.queue.empty() and self.interval and self.target() == target:
                await asyncio.sleep(self.interval)

    async def close(self, client=None, drain=True):
        if client is not None and self.client is not client:
            return
        if drain and self.worker is not None and not self.worker.done():
            try:
                await asyncio.wait_for(self.queue.join(), timeout=5)
            except asyncio.TimeoutError:
                pass
        if self.worker is not None:
            self.worker.cancel()
            await asyncio.gather(self.worker, return_exceptions=True)
        while not self.queue.empty():
            self.queue.get_nowait()
            self.queue.task_done()
        self.worker = None
        self.client = None
        self.peer = self.peer_target = None
        self.queue = asyncio.Queue(maxsize=100)

    def afk(self, event, sender, reason, duration, status="AFK"):
        chat = getattr(event, "chat", None)
        name = " ".join(filter(None, (getattr(sender, "first_name", ""), getattr(sender, "last_name", ""))))
        return self.emit("afk", {
            "chat": getattr(chat, "title", None) or str(getattr(event, "chat_id", "")),
            "sender": f"{name or getattr(sender, 'username', '')} ({event.sender_id})",
            "reason": reason or "—", "duration": duration, "status": status,
        }, link=message_link(event))

    @staticmethod
    def signature(config):
        return tuple(config.get(key, "") for key in CONFIG_KEYS)

    def panel(self, nonce, target, config):
        from telethon import Button
        lang = "en" if config.get("LANGUAGE") == "en" else "vi"
        kinds, fields = selections(config)
        enabled = str(config.get("LOG_CHAT_ID", "")) == str(target)
        text = get_text("log_panel", lang, target=target, status="✅ ON" if enabled else "❌ OFF", error=escape(self.last_error or "—"), dropped=self.dropped)
        rows = [[Button.inline(f"{'✅' if kind in kinds else '❌'} {LABELS[lang][kind]}", data=f"logcfg:{nonce}:cat_{kind}")] for kind in ("afk", "error", "update", "profile", "command")]
        rows += [[Button.inline(f"{'✅' if field in fields else '❌'} {LABELS[lang][field]}", data=f"logcfg:{nonce}:field_{field}")] for field in ("chat", "sender", "reason", "duration", "status")]
        rows.append([Button.inline(get_text("log_disable" if enabled else "log_enable", lang), data=f"logcfg:{nonce}:enabled")])
        return text, rows

    async def show_controls(self, target, state):
        if self.controls is None:
            return False
        nonce = secrets.token_hex(6)
        text, buttons = self.panel(nonce, target, state.config)
        card = {"target": target, "signature": self.signature(state.config), "inline": True, "inline_id": None}
        self.cards[nonce] = card
        while len(self.cards) > 32:
            self.cards.popitem(last=False)
        if self.client is not None and self.control_username and callable(getattr(self.client, "inline_query", None)):
            try:
                results = await asyncio.wait_for(self.client.inline_query(self.control_username, f"tgname_log {nonce}"), timeout=15)
                if results:
                    peer = await asyncio.wait_for(self.destination(target), timeout=15)
                    message = await asyncio.wait_for(results[0].click(peer, silent=True), timeout=15)
                    card.update(chat=target, message=getattr(message, "id", None))
                    return True
            except Exception:
                # /setinline chưa bật, chat cấm inline bot hoặc kết nối lỗi:
                # thử tin trực tiếp của Helper Bot, sau đó mới về chat admin.
                pass
        destinations = [target]
        admin = state.config.get("ADMIN_ID", "")
        if admin.isdigit() and int(admin) not in destinations:
            destinations.append(int(admin))
        for destination in destinations:
            try:
                message = await asyncio.wait_for(self.controls.send_message(destination, text, parse_mode="html", buttons=buttons, silent=True), timeout=10)
                if not isinstance(getattr(message, "id", None), int):
                    continue
                card.update(chat=destination, message=message.id, inline=False)
                return True
            except Exception:
                continue
        return False

    async def inline(self, event, state):
        parts = event.text.split()
        allowed = {str(state.config.get("ADMIN_ID", "")), str(state.account_id)}
        card = self.cards.get(parts[1]) if len(parts) == 2 and parts[0] == "tgname_log" else None
        if str(event.sender_id) not in allowed or state.is_resetting or not card or not card.get("inline") or card["signature"] != self.signature(state.config):
            await event.answer([], cache_time=0, private=True)
            return
        text, buttons = self.panel(parts[1], card["target"], state.config)
        result = await event.builder.article("🧾 Log settings", id="log_" + parts[1], text=text, parse_mode="html", buttons=buttons, link_preview=False)
        await event.answer([result], cache_time=0, private=True)

    async def button(self, event, state):
        from telethon.tl import types
        lang = state.config.get("LANGUAGE", "vi")
        allowed = {str(state.config.get("ADMIN_ID", "")), str(state.account_id)}
        if str(event.sender_id) not in allowed or state.is_resetting:
            await event.answer(get_text("log_denied", lang), alert=True)
            return
        parts = event.data.decode("ascii", errors="ignore").split(":")
        card = self.cards.get(parts[1]) if len(parts) == 3 else None
        inline_message = getattr(getattr(event, "query", None), "msg_id", None)
        is_inline = isinstance(inline_message, (types.InputBotInlineMessageID, types.InputBotInlineMessageID64))
        identity = tuple(getattr(inline_message, key, None) for key in ("dc_id", "id", "access_hash", "owner_id")) if is_inline else None
        valid_source = bool(card) and is_inline == card.get("inline", False)
        if valid_source and is_inline:
            valid_source = card["inline_id"] is None or card["inline_id"] == identity
        elif valid_source:
            valid_source = (card["chat"], card["message"]) == (event.chat_id, event.message_id)
        if not valid_source or card["signature"] != self.signature(state.config):
            await event.answer(get_text("log_expired", lang), alert=True)
            return
        if is_inline:
            card["inline_id"] = identity
        nonce, action = parts[1:]
        kinds, fields = selections(state.config)
        if action == "cat_afk":
            await event.answer(get_text("log_afk_required", lang), alert=True)
            return
        updates = {}
        if action.startswith("cat_") and action[4:] in LOG_TYPES:
            key = action[4:]
            kinds.symmetric_difference_update({key})
            updates["LOG_TYPES"] = ",".join(sorted(kinds | {"afk"}))
        elif action.startswith("field_") and action[6:] in AFK_FIELDS:
            fields.symmetric_difference_update({action[6:]})
            updates["LOG_AFK_FIELDS"] = ",".join(sorted(fields)) or "-"
        elif action == "enabled":
            updates["LOG_CHAT_ID"] = "" if self.target() == card["target"] else str(card["target"])
        else:
            return
        try:
            state.update_config(updates)
        except Exception:
            await event.answer(get_text("log_save_failed", lang), alert=True)
            return
        self.discard_pending()
        card["signature"] = self.signature(state.config)
        text, buttons = self.panel(nonce, card["target"], state.config)
        try:
            await event.edit(text, parse_mode="html", buttons=buttons)
            await event.answer()
        except Exception:
            self.cards.pop(nonce, None)
            await event.answer(get_text("log_panel_refresh", lang), alert=True)

    async def command(self, event, command, argument, client, state):
        self.bind(client, lambda: state.config)
        lang = state.config.get("LANGUAGE", "vi")
        target = self.target() or event.chat_id
        try:
            if command == "unloghere":
                if self.target() != event.chat_id:
                    await event.edit(get_text("log_not_here", lang), parse_mode="html")
                    return
                state.update_config({"LOG_CHAT_ID": ""})
                self.discard_pending()
            else:
                updates = {"LOG_CHAT_ID": str(event.chat_id)} if command == "loghere" else {}
                if argument:
                    kinds = set(re.split(r"[,\s]+", argument.strip().lower()))
                    if not kinds <= LOG_TYPES:
                        await event.edit(get_text("log_usage", lang), parse_mode="html")
                        return
                    updates["LOG_TYPES"] = ",".join(sorted(kinds | {"afk"}))
                if updates:
                    state.update_config(updates)
                    self.discard_pending()
                target = event.chat_id if command == "loghere" else self.target() or event.chat_id
            shown = await self.show_controls(target, state)
            await event.edit(get_text("log_configured", lang, target=target, status="✅ ON" if self.target() else "❌ OFF", kinds=", ".join(sorted(selections(state.config)[0]))) + ("" if shown else "\n" + get_text("log_no_controls", lang)), parse_mode="html")
        except Exception:
            await event.edit(get_text("log_save_failed", lang), parse_mode="html")


chat_log = ChatLogger()
