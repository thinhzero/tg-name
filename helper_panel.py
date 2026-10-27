"""Lệnh mới có tin riêng; nút/wizard/progress chỉ sửa đúng tin của phiên đó."""

import asyncio
from collections import OrderedDict

from telethon.errors import (
    MessageAuthorRequiredError, MessageEditTimeExpiredError,
    MessageIdInvalidError, MessageNotModifiedError,
)


MISSING_PANEL = (MessageAuthorRequiredError, MessageEditTimeExpiredError, MessageIdInvalidError)


class HelperPanels:
    def __init__(self, home_keyboard, history_limit=100):
        self.home_keyboard = home_keyboard
        self.chats = {}
        self.messages = OrderedDict()
        self.history_limit = history_limit

    @staticmethod
    def new_panel(edit=None):
        return {"edit": edit, "generation": 0, "lock": asyncio.Lock()}

    def remember_id(self, chat, message_id, panel):
        if not isinstance(message_id, int) or isinstance(message_id, bool):
            return
        key = (chat, message_id)
        self.messages[key] = panel
        self.messages.move_to_end(key)
        while len(self.messages) > self.history_limit:
            self.messages.popitem(last=False)

    def wrap(self, event, panel=None):
        chat = getattr(event, "chat_id", None) or event.sender_id
        if getattr(event, "data", None) is not None:
            message_id = getattr(event, "message_id", None)
            if isinstance(message_id, int) and not isinstance(message_id, bool):
                panel = self.messages.get((chat, message_id)) or self.new_panel()
                # Luôn nhắm tin có nút vừa bấm, không phải kết quả lệnh mới nhất.
                panel["edit"] = event.edit
                self.remember_id(chat, message_id, panel)
        elif getattr(event, "raw_text", "").lstrip().startswith("/"):
            panel = self.new_panel()
        if panel is None:
            panel = self.chats.get(chat) or self.new_panel()
        return PanelEvent(event, panel, self, chat)

    def remember(self, chat, message):
        panel = self.new_panel(message.edit)
        self.chats[chat] = panel
        self.remember_id(chat, getattr(message, "id", None), panel)


class PanelEvent:
    def __init__(self, event, panel, manager, chat):
        self.event = event
        self.panel = panel
        self.manager = manager
        self.chat = chat
        self.home_keyboard = manager.home_keyboard
        self.generation = panel["generation"]
        self.active = False
        self.visible = False
        self.message = PanelMessage(self)

    def __getattr__(self, key):
        return getattr(self.event, key)

    def remember_visible(self):
        if not self.visible:
            self.manager.chats[self.chat] = self.panel
            self.visible = True

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
                    self.remember_visible()
                    return self.message
                except MessageNotModifiedError:
                    self.panel["edit"] = edit
                    self.remember_visible()
                    return self.message
                except MISSING_PANEL:
                    self.panel["edit"] = None

            send = getattr(self.event, "respond" if fallback == "edit" else fallback)
            message = await send(text, silent=True, **kwargs)
            self.panel["edit"] = message.edit
            self.manager.remember_id(self.chat, getattr(message, "id", None), self.panel)
            self.remember_visible()
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
