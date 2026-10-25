"""Một tin nhắn giao diện cho mỗi chat; không sửa tin nhắn của người dùng."""

import asyncio

from telethon.errors import (
    MessageAuthorRequiredError, MessageEditTimeExpiredError,
    MessageIdInvalidError, MessageNotModifiedError,
)


MISSING_PANEL = (MessageAuthorRequiredError, MessageEditTimeExpiredError, MessageIdInvalidError)


class HelperPanels:
    def __init__(self, home_keyboard):
        self.home_keyboard = home_keyboard
        self.chats = {}

    def wrap(self, event):
        chat = getattr(event, "chat_id", None) or event.sender_id
        panel = self.chats.setdefault(chat, {"edit": None, "generation": 0, "lock": asyncio.Lock()})
        return PanelEvent(event, panel, self.home_keyboard)

    def remember(self, chat, message):
        panel = self.chats.setdefault(chat, {"edit": None, "generation": 0, "lock": asyncio.Lock()})
        panel["edit"] = message.edit


class PanelEvent:
    def __init__(self, event, panel, home_keyboard):
        self.event = event
        self.panel = panel
        self.home_keyboard = home_keyboard
        self.generation = panel["generation"]
        self.active = False
        self.message = PanelMessage(self)

    def __getattr__(self, key):
        return getattr(self.event, key)

    async def show(self, text, *, fallback="reply", **kwargs):
        async with self.panel["lock"]:
            if self.active:
                if self.generation != self.panel["generation"]:
                    return self.message
            else:
                if self.generation != self.panel["generation"]:
                    return self.message
                self.panel["generation"] += 1
                self.generation = self.panel["generation"]
                self.active = True

            if "buttons" not in kwargs:
                kwargs["buttons"] = self.home_keyboard()
            elif kwargs["buttons"] is not None:
                rows = [list(row) for row in kwargs["buttons"]]
                if not any(
                    (getattr(button, "data", None) or getattr(getattr(button, "type", None), "data", None)) == b"main_menu"
                    for row in rows for button in row
                ):
                    rows.extend(self.home_keyboard())
                kwargs["buttons"] = rows

            edit = self.panel["edit"]
            if edit is None and getattr(self.event, "data", None):
                edit = self.event.edit
            if edit is not None:
                try:
                    await edit(text, **kwargs)
                    self.panel["edit"] = edit
                    return self.message
                except MessageNotModifiedError:
                    self.panel["edit"] = edit
                    return self.message
                except MISSING_PANEL:
                    self.panel["edit"] = None

            send = getattr(self.event, "respond" if fallback == "edit" else fallback)
            message = await send(text, silent=True, **kwargs)
            self.panel["edit"] = message.edit
            return self.message

    async def reply(self, text, **kwargs):
        return await self.show(text, fallback="reply", **kwargs)

    async def respond(self, text, **kwargs):
        return await self.show(text, fallback="respond", **kwargs)

    async def edit(self, text, **kwargs):
        return await self.show(text, fallback="edit", **kwargs)

    async def show_pages(self, pages, page=0):
        if not pages or self.generation != self.panel["generation"]:
            return self.message
        self.panel["pages"] = pages
        page = min(max(page, 0), len(pages) - 1)
        from telethon import Button
        navigation = []
        if page:
            navigation.append(Button.inline("⬅️", data=f"panel_page:{page - 1}"))
        if page + 1 < len(pages):
            navigation.append(Button.inline("➡️", data=f"panel_page:{page + 1}"))
        return await self.show(pages[page], parse_mode="html", buttons=[navigation] if navigation else [])


class PanelMessage:
    def __init__(self, view):
        self.view = view

    async def edit(self, text, **kwargs):
        return await self.view.show(text, **kwargs)

    async def delete(self):
        # Status/progress cùng dùng panel: kết thúc một bước không xóa giao diện.
        # Tin nhắn chứa OTP/password vẫn xóa qua event gốc trong handler.
        return None
