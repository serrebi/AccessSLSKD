from __future__ import annotations

import threading
from typing import List, Optional, Tuple, Dict

import wx
from ..slsk_client import SlskService


class RoomsPanel(wx.Panel):
    def __init__(self, parent, service: SlskService, on_status):
        super().__init__(parent)
        self.service = service
        self.on_status = on_status
        self._avail_timer: Optional[wx.Timer] = None
        self._msg_timer: Optional[wx.Timer] = None
        self._msgs_in_progress = False
        self._last_msg_count: Dict[str, int] = {}
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

        # Available list
        tops.Add(wx.StaticText(self, label="Available Rooms (double-click to join):"), 0, wx.LEFT, 8)
        self.lstAvailable = wx.ListCtrl(self, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        self.lstAvailable.InsertColumn(0, "Room", width=420)
        self.lstAvailable.InsertColumn(1, "Users", width=70, format=wx.LIST_FORMAT_RIGHT)
        self.lstAvailable.InsertColumn(2, "Private", width=70)
        tops.Add(self.lstAvailable, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        # Joined list
        hdr = wx.BoxSizer(wx.HORIZONTAL)
        self.lblJoinedHeader = wx.StaticText(self, label="Joined Rooms:")
        self.lblJoinedSummary = wx.StaticText(self, label="")
        hdr.Add(self.lblJoinedHeader, 0, wx.RIGHT, 8)
        hdr.Add(self.lblJoinedSummary, 0, wx.ALIGN_CENTER_VERTICAL)
        tops.Add(hdr, 0, wx.LEFT, 8)
        self.lstRooms = wx.ListBox(self)
        tops.Add(self.lstRooms, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        # Selected room status
        self.lblSelectedStatus = wx.StaticText(self, label="")
        tops.Add(self.lblSelectedStatus, 0, wx.LEFT | wx.BOTTOM, 8)

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
        self.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_join_from_available, self.lstAvailable)

    def _with_status(self, msg: str):
        if callable(self.on_status):
            self.on_status(msg)

    # Activation from MainFrame (starts auto-refresh of the available list)
    def on_activated(self, active: bool):
        if active:
            if not self._avail_timer:
                self._avail_timer = wx.Timer(self)
                self.Bind(wx.EVT_TIMER, self._on_timer_available, self._avail_timer)
            if not self._msg_timer:
                self._msg_timer = wx.Timer(self)
                self.Bind(wx.EVT_TIMER, self._on_timer_messages, self._msg_timer)
            # Kick off immediate load, then every 60s
            self._load_available()
            self._on_refresh(None)
            self._avail_timer.Start(60000)
            # Auto-refresh messages for selected room every 3s
            self._msg_timer.Start(3000)
        else:
            if self._avail_timer:
                self._avail_timer.Stop()
            if self._msg_timer:
                self._msg_timer.Stop()

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

    def _on_timer_available(self, evt):
        self._load_available()

    def _on_timer_messages(self, evt):
        # Poll messages for the currently selected room
        if self._msgs_in_progress:
            return
        room = self._current_room()
        if not room:
            return
        self._msgs_in_progress = True
        def worker():
            try:
                msgs = self.service.rooms_messages(room)
                wx.CallAfter(self._display_messages, room, msgs)
            except Exception as e:
                wx.CallAfter(self._with_status, f"Load messages failed: {e}")
            finally:
                wx.CallAfter(self._mark_msgs_idle)
        threading.Thread(target=worker, daemon=True).start()

    def _mark_msgs_idle(self):
        self._msgs_in_progress = False

    def _load_available(self):
        def worker():
            try:
                infos = self.service.rooms_available() or []
                # Convert into tuples (name, userCount, private)
                rows: List[Tuple[str, int, bool]] = []
                for r in infos:
                    try:
                        rows.append((str(r.get("name","")), int(r.get("userCount", 0)), bool(r.get("isPrivate", False))))
                    except Exception:
                        pass
                # Sort by user count desc, then name
                rows.sort(key=lambda x: (-x[1], x[0].lower()))
                wx.CallAfter(self._fill_available, rows)
            except Exception as e:
                wx.CallAfter(self._with_status, f"Load rooms failed: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def _fill_available(self, rows: List[Tuple[str, int, bool]]):
        self.lstAvailable.Freeze()
        try:
            self.lstAvailable.DeleteAllItems()
            for (name, count, priv) in rows:
                idx = self.lstAvailable.InsertItem(self.lstAvailable.GetItemCount(), name)
                self.lstAvailable.SetItem(idx, 1, str(count))
                self.lstAvailable.SetItem(idx, 2, "Yes" if priv else "No")
        finally:
            self.lstAvailable.Thaw()
        self._with_status(f"{len(rows)} rooms available.")

    def _on_join_from_available(self, evt):
        idx = evt.GetIndex()
        if idx < 0:
            return
        name = self.lstAvailable.GetItemText(idx) or ""
        if not name:
            return
        self.txtRoom.SetValue(name)
        self._on_join(None)

    def _fill_rooms(self, names: List[str]):
        self.lstRooms.Set(names or [])
        count = len(names or [])
        self.lblJoinedSummary.SetLabel(f"({count} joined)")
        self._with_status(f"{count} rooms joined.")
        if names:
            self.lstRooms.SetSelection(0)
            self._load_messages(names[0])
            self._update_selected_status()
        else:
            self.lblSelectedStatus.SetLabel("Not joined.")

    def _current_room(self) -> str | None:
        sel = self.lstRooms.GetSelection()
        if sel == wx.NOT_FOUND:
            return None
        return self.lstRooms.GetString(sel)

    def _on_select_room(self, evt):
        name = self._current_room()
        if name:
            self._load_messages(name)
            self._update_selected_status()

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
        prev = int(self._last_msg_count.get(room, 0))
        cur = len(msgs or [])
        if cur != prev:
            # Re-render for simplicity; NVDA will read the update once.
            self.txtMessages.Clear()
            for m in msgs or []:
                self.txtMessages.AppendText(f"[{m.get('timestamp','')}] {m.get('username','')}: {m.get('message','')}\n")
            self._last_msg_count[room] = cur
            self._with_status(f"{cur} messages in {room}.")
        self._update_selected_status()

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

    def _update_selected_status(self):
        room = self._current_room()
        if not room:
            self.lblSelectedStatus.SetLabel("Selected: (none)")
            return
        # Assume rooms_joined() reflects truth; label to 'Joined' if present in list
        names = [self.lstRooms.GetString(i) for i in range(self.lstRooms.GetCount())]
        joined = room in names
        self.lblSelectedStatus.SetLabel(f"Selected: {room} — {'Joined' if joined else 'Not joined'}")
