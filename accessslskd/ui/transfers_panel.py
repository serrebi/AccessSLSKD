from __future__ import annotations

import threading
from typing import List

import wx
from slskd_api.apis._types import Transfer, TransferedDirectory, TransferedFile
from ..slsk_client import SlskService


class TransfersPanel(wx.Panel):
    def __init__(self, parent, service: SlskService, on_status, *, auto_update: bool = True, interval_sec: int = 5):
        super().__init__(parent)
        self.service = service
        self.on_status = on_status
        self._rows: list = []
        self._auto_enabled = bool(auto_update)
        self._interval_sec = max(1, int(interval_sec))
        # Cache username -> queueLength
        self._queue_cache: dict[str, int] = {}
        self._build_ui()
        self._build_context()

    def _build_ui(self):
        tops = wx.BoxSizer(wx.VERTICAL)

        row = wx.BoxSizer(wx.HORIZONTAL)
        self.btnRefresh = wx.Button(self, wx.ID_ANY, "&Refresh")
        self.btnCancel = wx.Button(self, wx.ID_ANY, "&Cancel Selected")
        self.btnPurge = wx.Button(self, wx.ID_ANY, "Remove &Completed")
        row.Add(self.btnRefresh, 0, wx.RIGHT, 6)
        row.Add(self.btnCancel, 0, wx.RIGHT, 6)
        row.Add(self.btnPurge, 0)
        tops.Add(row, 0, wx.ALL, 8)

        self.lst = wx.ListCtrl(self, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        self.lst.InsertColumn(0, "Dir", width=50)  # DL/UL
        self.lst.InsertColumn(1, "Username", width=140)
        self.lst.InsertColumn(2, "Directory", width=260)
        self.lst.InsertColumn(3, "File", width=320)
        self.lst.InsertColumn(4, "State", width=120)
        self.lst.InsertColumn(5, "%", width=60)
        self.lst.InsertColumn(6, "Speed", width=80)
        self.lst.InsertColumn(7, "ID", width=220)
        tops.Add(self.lst, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        self.SetSizer(tops)

        self.Bind(wx.EVT_BUTTON, self._on_refresh, self.btnRefresh)
        self.Bind(wx.EVT_BUTTON, self._on_cancel, self.btnCancel)
        self.Bind(wx.EVT_BUTTON, self._on_purge, self.btnPurge)
        self.lst.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK, self._on_right_click)
        self.Bind(wx.EVT_CONTEXT_MENU, self._on_context_menu)

        # Auto refresh timer
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_timer, self.timer)
        self._arm_timer()

    def _with_status(self, msg: str):
        if callable(self.on_status):
            self.on_status(msg)

    def _on_refresh(self, evt):
        self.btnRefresh.Disable()
        def worker():
            try:
                dls = self.service.list_downloads_all()
                uls = self.service.list_uploads_all()
                wx.CallAfter(self._after_refresh, dls, uls)
            except Exception as e:
                wx.CallAfter(self._after_error, f"Refresh failed: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def _after_refresh(self, downloads: List[Transfer], uploads: List[Transfer]):
        self._rows = []
        # Preserve selection, focus and scroll by key
        selected_ids = self._selected_ids()
        top_key = self._top_key()
        focus_key = self._focused_key()
        self.lst.Freeze()
        try:
            self.lst.DeleteAllItems()
            need_queue_for: set[str] = set()
            def append_rows(items, direction: str):
                for t in items or []:
                    username = t.get("username", "")
                    for d in (t.get("directories") or []):
                        dname = d.get("directory", "")
                        for f in (d.get("files") or []):
                            idx = self.lst.InsertItem(self.lst.GetItemCount(), "DL" if direction=="download" else "UL")
                            self.lst.SetItem(idx, 1, username)
                            self.lst.SetItem(idx, 2, dname)
                            self.lst.SetItem(idx, 3, f.get("filename", ""))
                            state = str(f.get("state", "") or "")
                            if direction == "download" and ("queue" in state.lower() or "queued" in state.lower()):
                                q = self._queue_cache.get(username)
                                if isinstance(q, int):
                                    state = f"{state} ({q})"
                                else:
                                    need_queue_for.add(username)
                            self.lst.SetItem(idx, 4, state)
                            self.lst.SetItem(idx, 5, f"{round(float(f.get('percentComplete', 0)),1)}")
                            self.lst.SetItem(idx, 6, str(round(float(f.get('averageSpeed', 0)),1)))
                            self.lst.SetItem(idx, 7, f.get("id", ""))
                            self._rows.append({"direction": direction, "username": username, "dir": dname, "file": f})
            append_rows(downloads, "download")
            append_rows(uploads, "upload")
            # Restore selection and focus
            if selected_ids:
                for i, r in enumerate(self._rows):
                    key = (r["direction"], r["username"], r["file"].get("id", ""))
                    if key in selected_ids:
                        self.lst.SetItemState(i, wx.LIST_STATE_SELECTED, wx.LIST_STATE_SELECTED)
            if focus_key:
                for i, r in enumerate(self._rows):
                    key = (r["direction"], r["username"], r["file"].get("id", ""))
                    if key == focus_key:
                        self.lst.Focus(i)
                        self.lst.EnsureVisible(i)
                        break
            if top_key:
                for i, r in enumerate(self._rows):
                    key = (r["direction"], r["username"], r["file"].get("id", ""))
                    if key == top_key:
                        self.lst.EnsureVisible(i)
                        break
            # If we need queue lengths for any usernames, fetch and update asynchronously
            if need_queue_for:
                self._refresh_queue_lengths(need_queue_for)
        finally:
            self.lst.Thaw()
        self.btnRefresh.Enable(True)
        self._with_status(f"{self.lst.GetItemCount()} transfer rows (downloads + uploads).")

    def _on_cancel(self, evt):
        idx = self.lst.GetFirstSelected()
        if idx == -1:
            self._with_status("Select a transfer to cancel.")
            return
        username = self.lst.GetItemText(idx, 1)
        file_id = self.lst.GetItemText(idx, 7)
        is_upload = (self.lst.GetItemText(idx, 0).upper() == "UL")
        self._with_status(f"Cancelling {file_id}...")
        def worker():
            try:
                if is_upload:
                    ok = self.service.cancel_upload(username, file_id, remove=False)
                else:
                    ok = self.service.cancel_download(username, file_id, remove=False)
                wx.CallAfter(self._with_status, "Cancelled." if ok else "Cancel failed.")
                wx.CallAfter(self._on_refresh, None)
            except Exception as e:
                wx.CallAfter(self._after_error, f"Cancel failed: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def _on_purge(self, evt):
        self._with_status("Removing completed downloads...")
        def worker():
            try:
                ok1 = self.service.remove_completed_downloads()
                ok2 = self.service.remove_completed_uploads()
                wx.CallAfter(self._with_status, "Cleared completed transfers." if (ok1 or ok2) else "Nothing removed.")
                wx.CallAfter(self._on_refresh, None)
            except Exception as e:
                wx.CallAfter(self._after_error, f"Purge failed: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def _after_error(self, msg: str):
        self.btnRefresh.Enable(True)
        self._with_status(msg)
        wx.Bell()

    # Context menu
    def _build_context(self):
        m = wx.Menu()
        self._miStart = m.Append(wx.ID_ANY, "&Start")
        self._miStop = m.Append(wx.ID_ANY, "S&top")
        self._miClear = m.Append(wx.ID_ANY, "Clear &Completed")
        m.AppendSeparator()
        self._miRemove = m.Append(wx.ID_ANY, "&Remove")
        self._miRemoveData = m.Append(wx.ID_ANY, "Remove &With Data")
        self._menu = m
        self.Bind(wx.EVT_MENU, self._on_start, self._miStart)
        self.Bind(wx.EVT_MENU, self._on_stop, self._miStop)
        self.Bind(wx.EVT_MENU, lambda e: self._on_purge(e), self._miClear)
        self.Bind(wx.EVT_MENU, self._on_remove, self._miRemove)
        self.Bind(wx.EVT_MENU, self._on_remove_data, self._miRemoveData)

    def _selected_row_info(self):
        idx = self.lst.GetFirstSelected()
        if idx == -1:
            return None
        # Align with _rows order (one entry per inserted row)
        if 0 <= idx < len(self._rows):
            return self._rows[idx]
        return None

    def _on_right_click(self, evt):
        # Enable/disable menu items based on direction
        idx = evt.GetIndex()
        if idx != -1:
            self.lst.Select(idx)
        info = self._selected_row_info()
        is_upload = info and info.get("direction") == "upload"
        # Start only makes sense for downloads
        self._miStart.Enable(not is_upload)
        self.PopupMenu(self._menu)

    def _on_context_menu(self, evt):
        # Keyboard menu key or right-click outside items: ensure a selection
        idx = self.lst.GetFirstSelected()
        if idx == -1 and self.lst.GetItemCount() > 0:
            self.lst.Select(0)
        info = self._selected_row_info()
        is_upload = info and info.get("direction") == "upload"
        self._miStart.Enable(not is_upload)
        self.PopupMenu(self._menu)

    def _on_start(self, evt):
        info = self._selected_row_info()
        if not info:
            self._with_status("Select a transfer first.")
            return
        if info.get("direction") == "upload":
            self._with_status("Start is only available for downloads.")
            return
        f = info["file"]
        files = [{"filename": f.get("filename", ""), "size": int(f.get("size", 0))}]
        self._with_status("Starting transfer…")
        def worker():
            try:
                ok = self.service.enqueue_downloads(info["username"], files)
                wx.CallAfter(self._with_status, "Started." if ok else "Start failed.")
                wx.CallAfter(self._on_refresh, None)
            except Exception as e:
                wx.CallAfter(self._after_error, f"Start failed: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def _on_stop(self, evt):
        idx = self.lst.GetFirstSelected()
        if idx == -1:
            self._with_status("Select a transfer first.")
            return
        username = self.lst.GetItemText(idx, 1)
        file_id = self.lst.GetItemText(idx, 7)
        is_upload = (self.lst.GetItemText(idx, 0).upper() == "UL")
        def worker():
            try:
                if is_upload:
                    ok = self.service.cancel_upload(username, file_id, remove=False)
                else:
                    ok = self.service.cancel_download(username, file_id, remove=False)
                wx.CallAfter(self._with_status, "Stopped." if ok else "Stop failed.")
                wx.CallAfter(self._on_refresh, None)
            except Exception as e:
                wx.CallAfter(self._after_error, f"Stop failed: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def _on_remove(self, evt):
        idx = self.lst.GetFirstSelected()
        if idx == -1:
            self._with_status("Select a transfer first.")
            return
        username = self.lst.GetItemText(idx, 1)
        file_id = self.lst.GetItemText(idx, 7)
        is_upload = (self.lst.GetItemText(idx, 0).upper() == "UL")
        def worker():
            try:
                if is_upload:
                    ok = self.service.cancel_upload(username, file_id, remove=True)
                else:
                    ok = self.service.cancel_download(username, file_id, remove=True)
                wx.CallAfter(self._with_status, "Removed." if ok else "Remove failed.")
                wx.CallAfter(self._on_refresh, None)
            except Exception as e:
                wx.CallAfter(self._after_error, f"Remove failed: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def _on_remove_data(self, evt):
        # Same as remove (server should remove transfer and any related data if applicable)
        self._on_remove(evt)

    def _selected_ids(self):
        ids = set()
        i = -1
        while True:
            i = self.lst.GetNextItem(i, wx.LIST_NEXT_ALL, wx.LIST_STATE_SELECTED)
            if i == -1:
                break
            ids.add((self.lst.GetItemText(i, 0).lower() == "ul" and "upload" or "download",
                     self.lst.GetItemText(i, 1),
                     self.lst.GetItemText(i, 7)))
        return ids

    def _arm_timer(self):
        self.timer.Stop()
        if self._auto_enabled:
            ms = max(1, int(self._interval_sec)) * 1000
            self.timer.Start(ms)

    def _on_timer(self, evt):
        # Avoid re-entrancy: if Refresh button is disabled, a fetch is in progress.
        if self.btnRefresh.IsEnabled():
            self._on_refresh(None)

    def _refresh_queue_lengths(self, usernames: set[str]):
        def worker(names: list[str]):
            updated: dict[str, int] = {}
            for u in names:
                try:
                    info = self.service.user_info(u)
                    q = int(info.get("queueLength", 0))
                    updated[u] = q
                except Exception:
                    continue
            if not updated:
                return
            def apply_updates():
                # Update cache
                self._queue_cache.update(updated)
                # Patch state column in-place for matching rows still visible
                for i, r in enumerate(self._rows):
                    if r.get("direction") != "download":
                        continue
                    base_state = str(r["file"].get("state","") or "")
                    if "queue" not in base_state.lower() and "queued" not in base_state.lower():
                        continue
                    u = r.get("username","")
                    if u in updated:
                        self.lst.SetItem(i, 4, f"{base_state} ({updated[u]})")
                self._with_status(f"Updated queue lengths for {len(updated)} user(s).")
            wx.CallAfter(apply_updates)
        threading.Thread(target=worker, args=(sorted(usernames),), daemon=True).start()

    def _top_key(self):
        top = self.lst.GetTopItem()
        if 0 <= top < len(self._rows):
            r = self._rows[top]
            return (r["direction"], r["username"], r["file"].get("id", ""))
        return None

    def _focused_key(self):
        idx = self.lst.GetNextItem(-1, wx.LIST_NEXT_ALL, wx.LIST_STATE_FOCUSED)
        if idx != -1 and 0 <= idx < len(self._rows):
            r = self._rows[idx]
            return (r["direction"], r["username"], r["file"].get("id", ""))
        sel = self.lst.GetNextItem(-1, wx.LIST_NEXT_ALL, wx.LIST_STATE_SELECTED)
        if sel != -1 and 0 <= sel < len(self._rows):
            r = self._rows[sel]
            return (r["direction"], r["username"], r["file"].get("id", ""))
        return None

    # Options integration
    def set_auto_update(self, enabled: bool):
        self._auto_enabled = bool(enabled)
        self._arm_timer()

    def set_interval(self, seconds: int):
        self._interval_sec = max(1, int(seconds))
        self._arm_timer()
