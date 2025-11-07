from __future__ import annotations

import threading
from typing import Any, Dict, List

import wx

from ..slsk_client import SlskService


class UserBrowserFrame(wx.Frame):
    def __init__(self, parent, service: SlskService, username: str, on_status):
        super().__init__(parent, title=f"Browse: {username}", size=(1000, 700))
        self.service = service
        self.username = username
        self.on_status = on_status
        self._build_ui()
        self._load_root()

    def _build_ui(self):
        panel = wx.Panel(self)
        tops = wx.BoxSizer(wx.VERTICAL)

        # Path bar and buttons
        prow = wx.BoxSizer(wx.HORIZONTAL)
        self.lblUser = wx.StaticText(panel, label=f"User: {self.username}")
        self.txtPath = wx.TextCtrl(panel)
        self.btnGo = wx.Button(panel, wx.ID_ANY, "&Open")
        self.btnUp = wx.Button(panel, wx.ID_ANY, "&Up")
        prow.Add(self.lblUser, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        prow.Add(wx.StaticText(panel, label="Path (&P):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        prow.Add(self.txtPath, 1, wx.RIGHT, 6)
        prow.Add(self.btnGo, 0, wx.RIGHT, 6)
        prow.Add(self.btnUp, 0)
        tops.Add(prow, 0, wx.EXPAND | wx.ALL, 8)

        splitter = wx.SplitterWindow(panel, style=wx.SP_LIVE_UPDATE | wx.SP_3D)
        self.tree = wx.TreeCtrl(splitter, style=wx.TR_HAS_BUTTONS | wx.TR_LINES_AT_ROOT | wx.TR_DEFAULT_STYLE)
        self.list = wx.ListCtrl(splitter, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        self.list.InsertColumn(0, "Name", width=520)
        self.list.InsertColumn(1, "Size", width=140)
        self.list.InsertColumn(2, "Type", width=100)
        splitter.SplitVertically(self.tree, self.list, sashPosition=320)
        splitter.SetMinimumPaneSize(150)
        tops.Add(splitter, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        # Buttons row
        brow = wx.BoxSizer(wx.HORIZONTAL)
        self.btnDownloadSelected = wx.Button(panel, wx.ID_ANY, "Download &Selected File(s)")
        self.btnDownloadDir = wx.Button(panel, wx.ID_ANY, "Download &Directory")
        brow.Add(self.btnDownloadSelected, 0, wx.RIGHT, 6)
        brow.Add(self.btnDownloadDir, 0)
        tops.Add(brow, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        panel.SetSizer(tops)

        # Context menu
        self._menu = wx.Menu()
        self._miDownload = self._menu.Append(wx.ID_ANY, "Download &File(s)")
        self._miDownloadDir = self._menu.Append(wx.ID_ANY, "Download &Directory")
        self.list.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK, lambda e: self.PopupMenu(self._menu))
        self.Bind(wx.EVT_MENU, lambda e: self._on_download_selected(e), self._miDownload)
        self.Bind(wx.EVT_MENU, lambda e: self._on_download_dir(e), self._miDownloadDir)

        # Events
        self.Bind(wx.EVT_BUTTON, self._on_open, self.btnGo)
        self.Bind(wx.EVT_TEXT_ENTER, self._on_open, self.txtPath)
        self.Bind(wx.EVT_BUTTON, self._on_up, self.btnUp)
        self.Bind(wx.EVT_BUTTON, self._on_download_selected, self.btnDownloadSelected)
        self.Bind(wx.EVT_BUTTON, self._on_download_dir, self.btnDownloadDir)
        self.tree.Bind(wx.EVT_TREE_ITEM_EXPANDING, self._on_expand)
        self.tree.Bind(wx.EVT_TREE_SEL_CHANGED, self._on_tree_select)

    def _status(self, msg: str):
        if callable(self.on_status):
            self.on_status(msg)

    def _load_root(self):
        self._status("Loading user root…")
        def worker():
            try:
                root = self.service.browse_user_root(self.username)
                wx.CallAfter(self._after_root, root)
            except Exception as e:
                wx.CallAfter(self._status, f"Browse failed: {e}")
                wx.Bell()
        threading.Thread(target=worker, daemon=True).start()

    def _after_root(self, root):
        self.tree.DeleteAllItems()
        root_id = self.tree.AddRoot(self.username)
        for d in (root.get("directories") or []):
            child = self.tree.AppendItem(root_id, d.get("name", ""))
            self.tree.SetItemData(child, ("dir", d.get("name", "")))
            self.tree.SetItemHasChildren(child, True)
        for d in (root.get("lockedDirectories") or []):
            child = self.tree.AppendItem(root_id, d.get("name", ""))
            self.tree.SetItemData(child, ("dir", d.get("name", "")))
            self.tree.SetItemHasChildren(child, True)
        self.tree.Expand(root_id)
        self.list.DeleteAllItems()
        self.txtPath.SetValue("")
        self._status("Loaded root.")

    def _on_expand(self, evt):
        item = evt.GetItem()
        data = self.tree.GetItemData(item)
        if isinstance(data, (tuple, list)) and len(data) >= 2:
            kind, name = data[0], data[1]
        else:
            # Be tolerant: some items (like the root) may not have data attached.
            # Treat as a directory node using its label as the name.
            kind, name = "dir", self.tree.GetItemText(item)
        # Build path from tree lineage
        path = self._path_from_item(item)
        self._open_path(path, update_tree=item)

    def _path_from_item(self, item) -> str:
        parts = []
        while item and item.IsOk() and self.tree.GetItemParent(item).IsOk():
            data = self.tree.GetItemData(item)
            if isinstance(data, (tuple, list)) and len(data) >= 2 and data[0] == "dir":
                parts.append(data[1])
            else:
                # Fallback to the visual label
                parts.append(self.tree.GetItemText(item))
            item = self.tree.GetItemParent(item)
        parts.reverse()
        sep = "\\"
        return sep.join(parts)

    def _on_tree_select(self, evt):
        item = evt.GetItem()
        path = self._path_from_item(item)
        self.txtPath.SetValue(path)
        if path:
            self._open_path(path)

    def _on_open(self, evt):
        path = self.txtPath.GetValue().strip()
        self._open_path(path)

    def _on_up(self, evt):
        p = self.txtPath.GetValue().strip()
        if not p:
            return
        newp = p.rstrip("\\/").rsplit("\\", 1)[0] if "\\" in p else p.rstrip("/").rsplit("/", 1)[0]
        self.txtPath.SetValue(newp)
        self._open_path(newp)

    def _open_path(self, path: str, update_tree=None):
        self._status(f"Loading {path or '/'} …")
        def worker():
            try:
                listing = self.service.user_directory(self.username, path)
                wx.CallAfter(self._after_open, path, listing, update_tree)
            except Exception as e:
                wx.CallAfter(self._status, f"Open failed: {e}")
                wx.Bell()
        threading.Thread(target=worker, daemon=True).start()

    def _after_open(self, path: str, listing, update_tree):
        # listing is a list (usually 1 element)
        self.list.DeleteAllItems()
        if not listing:
            self._status("No entries.")
            return
        d = listing[0]
        # Populate list with files and subdirectories if present
        for sub in (d.get("directories") or []):
            idx = self.list.InsertItem(self.list.GetItemCount(), sub.get("name", ""))
            self.list.SetItem(idx, 1, "")
            self.list.SetItem(idx, 2, "Dir")
        for f in (d.get("files") or []):
            idx = self.list.InsertItem(self.list.GetItemCount(), f.get("filename", ""))
            self.list.SetItem(idx, 1, str(f.get("size", 0)))
            self.list.SetItem(idx, 2, "File")
        # Update tree children (lazy)
        if update_tree:
            self.tree.DeleteChildren(update_tree)
            for sub in (d.get("directories") or []):
                child = self.tree.AppendItem(update_tree, sub.get("name", ""))
                self.tree.SetItemData(child, ("dir", sub.get("name", "")))
                self.tree.SetItemHasChildren(child, True)
        self._status(f"Opened {path or '/'}")

    def _selected_files(self) -> List[Dict[str, Any]]:
        files = []
        i = -1
        current_dir = self.txtPath.GetValue().strip()
        while True:
            i = self.list.GetNextItem(i, wx.LIST_NEXT_ALL, wx.LIST_STATE_SELECTED)
            if i == -1:
                break
            t = self.list.GetItemText(i, 2)
            if t.lower() == "file":
                name = self.list.GetItemText(i, 0)
                size = int(self.list.GetItemText(i, 1) or "0")
                sep = "\\" if "\\" in current_dir else "/"
                full = name if (name.startswith("\\") or name.startswith("/") or ":" in name) else (current_dir.rstrip("\\/") + sep + name if current_dir else name)
                files.append({"filename": full, "size": size})
        return files

    def _on_download_selected(self, evt):
        files = self._selected_files()
        if not files:
            self._status("Select file(s) to download.")
            return
        self._status(f"Enqueueing {len(files)} file(s)…")
        def worker():
            try:
                ok = self.service.enqueue_downloads(self.username, files)
                wx.CallAfter(self._status, "Enqueued." if ok else "Enqueue failed.")
            except Exception as e:
                wx.CallAfter(self._status, f"Enqueue failed: {e}")
                wx.Bell()
        threading.Thread(target=worker, daemon=True).start()

    def _on_download_dir(self, evt):
        path = self.txtPath.GetValue().strip()
        if not path:
            self._status("Open a directory first.")
            return
        self._status(f"Enqueueing directory {path}…")
        def worker():
            try:
                n = self.service.enqueue_directory(self.username, path)
                wx.CallAfter(self._status, f"Enqueued {n} file(s) from {path}.")
            except Exception as e:
                wx.CallAfter(self._status, f"Directory enqueue failed: {e}")
                wx.Bell()
        threading.Thread(target=worker, daemon=True).start()
