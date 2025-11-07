from __future__ import annotations

import threading
from typing import List

import wx
from ..slsk_client import SlskService


class RoomsPanel(wx.Panel):
    def __init__(self, parent, service: SlskService, on_status):
        super().__init__(parent)
        self.service = service
        self.on_status = on_status
        self._build_ui()

    def _build_ui(self):
        tops = wx.BoxSizer(wx.VERTICAL)

        # Join/Leave row
        jrow = wx.BoxSizer(wx.HORIZONTAL)
        self.lblRoom = wx.StaticText(self, label="Room (&R):")
        self.txtRoom = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.btnJoin = wx.Button(self, wx.ID_ANY, "&Join")
        self.btnLeave = wx.Button(self, wx.ID_ANY, "&Leave")
        self.btnRefresh = wx.Button(self, wx.ID_ANY, "&Refresh")
        jrow.Add(self.lblRoom, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        jrow.Add(self.txtRoom, 1, wx.RIGHT, 6)
        jrow.Add(self.btnJoin, 0, wx.RIGHT, 6)
        jrow.Add(self.btnLeave, 0, wx.RIGHT, 6)
        jrow.Add(self.btnRefresh, 0)
        tops.Add(jrow, 0, wx.EXPAND | wx.ALL, 8)

        # Joined list
        tops.Add(wx.StaticText(self, label="Joined Rooms:"), 0, wx.LEFT, 8)
        self.lstRooms = wx.ListBox(self)
        tops.Add(self.lstRooms, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        # Messages + send
        tops.Add(wx.StaticText(self, label="Messages:"), 0, wx.LEFT, 8)
        self.txtMessages = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.VSCROLL)
        tops.Add(self.txtMessages, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        srow = wx.BoxSizer(wx.HORIZONTAL)
        self.lblMsg = wx.StaticText(self, label="Message (&M):")
        self.txtMsg = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.btnSend = wx.Button(self, wx.ID_ANY, "&Send")
        srow.Add(self.lblMsg, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        srow.Add(self.txtMsg, 1, wx.RIGHT, 6)
        srow.Add(self.btnSend, 0)
        tops.Add(srow, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        self.SetSizer(tops)

        self.Bind(wx.EVT_BUTTON, self._on_join, self.btnJoin)
        self.Bind(wx.EVT_BUTTON, self._on_leave, self.btnLeave)
        self.Bind(wx.EVT_TEXT_ENTER, self._on_join, self.txtRoom)
        self.Bind(wx.EVT_BUTTON, self._on_refresh, self.btnRefresh)
        self.Bind(wx.EVT_LISTBOX, self._on_select_room, self.lstRooms)
        self.Bind(wx.EVT_BUTTON, self._on_send, self.btnSend)
        self.Bind(wx.EVT_TEXT_ENTER, self._on_send, self.txtMsg)

    def _with_status(self, msg: str):
        if callable(self.on_status):
            self.on_status(msg)

    def _on_join(self, evt):
        name = self.txtRoom.GetValue().strip()
        if not name:
            self._with_status("Enter a room name.")
            return
        def worker():
            try:
                self.service.rooms_join(name)
                wx.CallAfter(self._with_status, f"Joined {name}.")
                wx.CallAfter(self._on_refresh, None)
            except Exception as e:
                wx.CallAfter(self._with_status, f"Join failed: {e}")
                wx.Bell()
        threading.Thread(target=worker, daemon=True).start()

    def _on_leave(self, evt):
        name = self._current_room() or self.txtRoom.GetValue().strip()
        if not name:
            self._with_status("Select or enter a room.")
            return
        def worker():
            try:
                ok = self.service.rooms_leave(name)
                wx.CallAfter(self._with_status, f"Left {name}." if ok else f"Leave failed for {name}.")
                wx.CallAfter(self._on_refresh, None)
            except Exception as e:
                wx.CallAfter(self._with_status, f"Leave failed: {e}")
                wx.Bell()
        threading.Thread(target=worker, daemon=True).start()

    def _on_refresh(self, evt):
        def worker():
            try:
                joined = self.service.rooms_joined()
                wx.CallAfter(self._fill_rooms, joined)
            except Exception as e:
                wx.CallAfter(self._with_status, f"Refresh failed: {e}")
                wx.Bell()
        threading.Thread(target=worker, daemon=True).start()

    def _fill_rooms(self, names: List[str]):
        self.lstRooms.Set(names or [])
        self._with_status(f"{len(names or [])} rooms joined.")
        if names:
            self.lstRooms.SetSelection(0)
            self._load_messages(names[0])

    def _current_room(self) -> str | None:
        sel = self.lstRooms.GetSelection()
        if sel == wx.NOT_FOUND:
            return None
        return self.lstRooms.GetString(sel)

    def _on_select_room(self, evt):
        name = self._current_room()
        if name:
            self._load_messages(name)

    def _load_messages(self, room: str):
        self._with_status(f"Loading messages for {room}...")
        def worker():
            try:
                msgs = self.service.rooms_messages(room)
                wx.CallAfter(self._display_messages, room, msgs)
            except Exception as e:
                wx.CallAfter(self._with_status, f"Load messages failed: {e}")
                wx.Bell()
        threading.Thread(target=worker, daemon=True).start()

    def _display_messages(self, room: str, msgs):
        self.txtMessages.Clear()
        for m in msgs or []:
            self.txtMessages.AppendText(f"[{m.get('timestamp','')}] {m.get('username','')}: {m.get('message','')}\n")
        self._with_status(f"{len(msgs or [])} messages in {room}.")

    def _on_send(self, evt):
        room = self._current_room()
        if not room:
            self._with_status("Select a room to send a message.")
            return
        msg = self.txtMsg.GetValue().strip()
        if not msg:
            self._with_status("Type a message first.")
            return
        def worker():
            try:
                ok = self.service.rooms_send(room, msg)
                wx.CallAfter(self._with_status, "Message sent." if ok else "Send failed.")
                wx.CallAfter(self.txtMsg.Clear)
                wx.CallAfter(self._load_messages, room)
            except Exception as e:
                wx.CallAfter(self._with_status, f"Send failed: {e}")
                wx.Bell()
        threading.Thread(target=worker, daemon=True).start()

