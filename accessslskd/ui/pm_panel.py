from __future__ import annotations

import threading
from typing import List

import wx
from slskd_api.apis._types import Conversation
from ..slsk_client import SlskService


class PmPanel(wx.Panel):
    def __init__(self, parent, service: SlskService, on_status):
        super().__init__(parent)
        self.service = service
        self.on_status = on_status
        self._build_ui()

    def _build_ui(self):
        tops = wx.BoxSizer(wx.VERTICAL)

        # Conversations list
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.btnRefresh = wx.Button(self, wx.ID_ANY, "&Refresh")
        row.Add(self.btnRefresh, 0)
        tops.Add(row, 0, wx.ALL, 8)

        self.lstConvs = wx.ListCtrl(self, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        self.lstConvs.InsertColumn(0, "Username", width=200)
        self.lstConvs.InsertColumn(1, "Unacked", width=100)
        tops.Add(self.lstConvs, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        tops.Add(wx.StaticText(self, label="Message History:"), 0, wx.LEFT, 8)
        self.txtHistory = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.VSCROLL)
        tops.Add(self.txtHistory, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        srow = wx.BoxSizer(wx.HORIZONTAL)
        self.lblUser = wx.StaticText(self, label="To (&T):")
        self.txtUser = wx.TextCtrl(self)
        self.lblMsg = wx.StaticText(self, label="Message (&M):")
        self.txtMsg = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.btnSend = wx.Button(self, wx.ID_ANY, "&Send")
        srow.Add(self.lblUser, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        srow.Add(self.txtUser, 0, wx.RIGHT, 10)
        srow.Add(self.lblMsg, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        srow.Add(self.txtMsg, 1, wx.RIGHT, 6)
        srow.Add(self.btnSend, 0)
        tops.Add(srow, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        self.SetSizer(tops)

        self.Bind(wx.EVT_BUTTON, self._on_refresh, self.btnRefresh)
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_select, self.lstConvs)
        self.Bind(wx.EVT_BUTTON, self._on_send, self.btnSend)
        self.Bind(wx.EVT_TEXT_ENTER, self._on_send, self.txtMsg)

    def _with_status(self, msg: str):
        if callable(self.on_status):
            self.on_status(msg)

    def _on_refresh(self, evt):
        def worker():
            try:
                convs = self.service.conversations()
                wx.CallAfter(self._fill_convs, convs)
            except Exception as e:
                wx.CallAfter(self._with_status, f"Refresh failed: {e}")
                wx.Bell()
        threading.Thread(target=worker, daemon=True).start()

    def _fill_convs(self, convs: List[Conversation]):
        self.lstConvs.Freeze()
        try:
            self.lstConvs.DeleteAllItems()
            for c in convs or []:
                idx = self.lstConvs.InsertItem(self.lstConvs.GetItemCount(), c.get("username", ""))
                self.lstConvs.SetItem(idx, 1, str(c.get("unAcknowledgedMessageCount", 0)))
        finally:
            self.lstConvs.Thaw()
        self._with_status(f"{self.lstConvs.GetItemCount()} conversations.")

    def _on_select(self, evt):
        user = self.lstConvs.GetItemText(evt.GetIndex())
        self.txtUser.SetValue(user)
        # Fetch messages by conversation
        def worker():
            try:
                conv = self.service._client.conversations.get(user, includeMessages=True)
                msgs = conv.get("messages", []) or []
                wx.CallAfter(self._fill_history, msgs)
            except Exception as e:
                wx.CallAfter(self._with_status, f"Load history failed: {e}")
                wx.Bell()
        threading.Thread(target=worker, daemon=True).start()

    def _fill_history(self, msgs):
        self.txtHistory.Clear()
        for m in msgs:
            who = "Me" if m.get("direction") == "Out" else m.get("username", "")
            self.txtHistory.AppendText(f"[{m.get('timestamp','')}] {who}: {m.get('message','')}\n")

    def _on_send(self, evt):
        user = self.txtUser.GetValue().strip()
        msg = self.txtMsg.GetValue().strip()
        if not user:
            self._with_status("Enter a username.")
            return
        if not msg:
            self._with_status("Type a message.")
            return
        def worker():
            try:
                ok = self.service.pm_send(user, msg)
                wx.CallAfter(self._with_status, "Private message sent." if ok else "Send failed.")
                wx.CallAfter(self.txtMsg.Clear)
                wx.CallAfter(self._on_refresh, None)
            except Exception as e:
                wx.CallAfter(self._with_status, f"Send failed: {e}")
                wx.Bell()
        threading.Thread(target=worker, daemon=True).start()

