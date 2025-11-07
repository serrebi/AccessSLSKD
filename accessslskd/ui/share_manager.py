from __future__ import annotations

import os
import threading
from typing import Dict, List

import wx

try:
    import yaml  # type: ignore
except Exception as _yaml_err:
    yaml = None  # type: ignore

from ..slsk_client import SlskService


class ShareManagerDialog(wx.Dialog):
    def __init__(self, parent, service: SlskService):
        super().__init__(parent, title="Share Manager", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER, size=(720, 520))
        self.service = service
        self._yaml_text = ""
        self._yaml_obj = {}
        # Map normalized local path -> existing alias (from slskd), if any
        self._existing_aliases: Dict[str, str] = {}
        # In-memory items shown in the list control
        self._share_items: List[Dict[str, str]] = []
        self._build_ui()
        self._load_data()

    def _build_ui(self):
        pnl = wx.Panel(self)
        tops = wx.BoxSizer(wx.VERTICAL)

        # Downloads location
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(pnl, label="Downloads Folder (&D):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.txtDownloads = wx.TextCtrl(pnl)
        self.btnBrowse = wx.Button(pnl, wx.ID_ANY, "&Browse…")
        row.Add(self.txtDownloads, 1, wx.RIGHT, 6)
        row.Add(self.btnBrowse, 0)
        tops.Add(row, 0, wx.EXPAND | wx.ALL, 8)

        # Shares list
        tops.Add(wx.StaticText(pnl, label="Shared Folders:"), 0, wx.LEFT, 8)
        self.lst = wx.ListCtrl(pnl, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        self.lst.InsertColumn(0, "Alias", width=240)
        self.lst.InsertColumn(1, "Path", width=460)
        tops.Add(self.lst, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        # Buttons row
        brow = wx.BoxSizer(wx.HORIZONTAL)
        self.btnAdd = wx.Button(pnl, wx.ID_ANY, "&Add Folder…")
        self.btnEdit = wx.Button(pnl, wx.ID_ANY, "Edit &Alias…")
        self.btnRemove = wx.Button(pnl, wx.ID_ANY, "&Remove Selected")
        self.btnRescan = wx.Button(pnl, wx.ID_ANY, "Re&scan Shares")
        brow.Add(self.btnAdd, 0, wx.RIGHT, 6)
        brow.Add(self.btnEdit, 0, wx.RIGHT, 6)
        brow.Add(self.btnRemove, 0, wx.RIGHT, 6)
        brow.Add(self.btnRescan, 0)
        tops.Add(brow, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        pnl.SetSizer(tops)

        btns = self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL)
        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(pnl, 1, wx.EXPAND | wx.ALL, 6)
        if btns:
            root.Add(btns, 0, wx.EXPAND | wx.ALL, 6)
        self.SetSizer(root)
        self.Layout()

        # Events
        self.Bind(wx.EVT_BUTTON, self._on_browse_downloads, self.btnBrowse)
        self.Bind(wx.EVT_BUTTON, self._on_add, self.btnAdd)
        self.Bind(wx.EVT_BUTTON, self._on_remove, self.btnRemove)
        self.Bind(wx.EVT_BUTTON, self._on_edit_alias, self.btnEdit)
        self.Bind(wx.EVT_BUTTON, self._on_rescan, self.btnRescan)
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)

    def _status(self, msg: str):
        try:
            self.GetParent().SetStatusText(msg, 0)
        except Exception:
            pass

    def _load_data(self):
        if yaml is None:
            wx.MessageBox(
                "PyYAML is required for Share Manager.\n\n"
                "Install with:\n  python -m pip install PyYAML",
                "Missing Dependency",
                wx.OK | wx.ICON_WARNING,
                parent=self,
            )
            return
        self._status("Loading shares and options...")
        def worker():
            try:
                # YAML (remote configuration)
                yml = self.service.options_download_yaml()
                shares = self.service.shares_list()
                wx.CallAfter(self._after_load, yml, shares)
            except Exception as e:
                wx.CallAfter(self._after_error, f"Load failed: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def _after_load(self, yaml_text: str, shares: dict):
        self._yaml_text = yaml_text or ""
        if yaml:
            try:
                self._yaml_obj = yaml.safe_load(self._yaml_text) or {}
            except Exception:
                self._yaml_obj = {}
        # Downloads folder: directories.downloads in YAML if present
        downloads = ""
        try:
            directories = self._yaml_obj.get("directories", {}) or {}
            downloads = directories.get("downloads", "") or ""
        except Exception:
            downloads = ""
        self.txtDownloads.SetValue(str(downloads))
        # Shares list via API read (more reliable current state)
        self._existing_aliases = {}
        paths: List[str] = []
        try:
            for s in (shares.get("local") or []):
                p = s.get("localPath") or s.get("raw") or s.get("remotePath")
                if p:
                    paths.append(p)
                    alias = (s.get("alias") or "").strip()
                    if alias:
                        self._existing_aliases[p.lower()] = alias
        except Exception:
            pass
        if not paths:
            # Fallback to YAML if API doesn't give anything
            try:
                paths = [p for p in (self._yaml_obj.get("shares", {}).get("directories") or []) if isinstance(p, str)]
            except Exception:
                paths = []
        # Build items and render
        self._share_items = [{"path": p, "alias": self._existing_aliases.get(p.lower(), "")} for p in paths]
        self._render_list()
        self._status("Ready.")

    def _on_browse_downloads(self, evt):
        with wx.DirDialog(self, "Choose Downloads Folder") as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self.txtDownloads.SetValue(dlg.GetPath())

    def _on_add(self, evt):
        with wx.DirDialog(self, "Add Folder to Share") as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                p = dlg.GetPath().strip()
                if not p:
                    return
                # Prevent duplicates (case-insensitive)
                if any((it.get("path","").lower() == p.lower()) for it in self._share_items):
                    return
                alias = self._existing_aliases.get(p.lower(), "")
                self._share_items.append({"path": p, "alias": alias})
                self._render_list(select_index=len(self._share_items)-1)

    def _on_remove(self, evt):
        # Remove selected row(s)
        idx = -1
        removed = False
        while True:
            idx = self.lst.GetNextItem(idx, wx.LIST_NEXT_ALL, wx.LIST_STATE_SELECTED)
            if idx == -1:
                break
            if 0 <= idx < len(self._share_items):
                self._share_items.pop(idx)
                removed = True
                idx = -1  # restart because indices shift
        if removed:
            self._render_list()

    def _on_edit_alias(self, evt):
        idx = self.lst.GetNextItem(-1, wx.LIST_NEXT_ALL, wx.LIST_STATE_SELECTED)
        if idx == -1 or not (0 <= idx < len(self._share_items)):
            self._status("Select a folder to edit its alias.")
            return
        cur_alias = self._share_items[idx].get("alias", "")
        new_alias = wx.GetTextFromUser("Alias (optional):", "Edit Alias", cur_alias, parent=self)
        if new_alias is None:
            return
        self._share_items[idx]["alias"] = new_alias.strip()
        self._render_list(select_index=idx)

    def _on_rescan(self, evt):
        self._status("Rescanning shares...")
        def worker():
            try:
                ok = self.service.shares_rescan()
                wx.CallAfter(self._status, "Rescan started." if ok else "Rescan request failed.")
            except Exception as e:
                wx.CallAfter(self._after_error, f"Rescan failed: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def _on_ok(self, evt):
        # Build new YAML from existing, updating directories.downloads and shares.directories
        cfg = dict(self._yaml_obj or {})
        # Ensure container keys
        directories = dict(cfg.get("directories") or {})
        directories["downloads"] = self.txtDownloads.GetValue().strip()
        cfg["directories"] = directories
        shares = dict(cfg.get("shares") or {})
        # Normalize and de-duplicate share items by path
        seen = set()
        items: List[Dict[str, str]] = []
        for it in self._share_items:
            p = (it.get("path") or "").strip()
            a = (it.get("alias") or "").strip()
            if not p:
                continue
            if p.lower() in seen:
                continue
            seen.add(p.lower())
            items.append({"path": p, "alias": a})

        # Build alias-encoded list:
        # - Preserve existing aliases from slskd when present.
        # - Auto-alias when multiple entries share the same leaf directory name (case-insensitive).
        def _leaf(path: str) -> str:
            q = path.rstrip("\\/")
            return os.path.basename(q) or q

        # Group by leaf name
        groups: Dict[str, List[str]] = {}
        for it in items:
            p = it["path"]
            groups.setdefault(_leaf(p).lower(), []).append(p)

        encoded_paths: List[str] = []
        for key, plist in groups.items():
            if len(plist) == 1:
                path = plist[0]
                # Prefer explicit alias then existing slskd alias
                alias = next((it["alias"] for it in items if it["path"].lower() == path.lower() and it.get("alias")), "")
                if not alias:
                    alias = (self._existing_aliases.get(path.lower()) or "").strip()
                if alias:
                    encoded_paths.append(f"[{alias}]{path}")
                else:
                    encoded_paths.append(path)
                continue
            # Multiple with same leaf name; generate deterministic aliases
            for idx, path in enumerate(sorted(plist, key=lambda s: s.lower()), start=1):
                base = _leaf(path)
                # Prefer explicit alias then existing slskd alias
                alias = next((it["alias"] for it in items if it["path"].lower() == path.lower() and it.get("alias")), "")
                if not alias:
                    alias = (self._existing_aliases.get(path.lower()) or "").strip()
                if not alias:
                    drive, _ = os.path.splitdrive(path)
                    if drive:
                        suffix = drive.rstrip(":\\/").upper()
                    else:
                        norm = path.replace("/", "\\")
                        if norm.startswith("\\\\"):
                            parts = [x for x in norm.split("\\") if x]
                            suffix = (parts[1] if len(parts) > 1 else "UNC").upper()
                        else:
                            parts = [x for x in path.split("/") if x]
                            suffix = (parts[0] if parts else str(idx)).upper()
                    alias = f"{base} ({suffix})"
                encoded_paths.append(f"[{alias}]{path}")

        shares["directories"] = encoded_paths
        cfg["shares"] = shares
        if yaml:
            try:
                dumped = yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True)
            except Exception as e:
                wx.MessageBox(f"Failed to encode YAML:\n{e}", "Error", wx.OK | wx.ICON_ERROR, parent=self)
                return
        else:
            wx.MessageBox("PyYAML not available.", "Error", wx.OK | wx.ICON_ERROR, parent=self)
            return
        # Validate YAML via API (server-side)
        try:
            msg = self.service.options_validate_yaml(dumped)
            if msg and msg.strip():
                wx.MessageBox(f"slskd rejected the configuration:\n\n{msg}", "Validation Failed", wx.OK | wx.ICON_ERROR, parent=self)
                return
        except Exception:
            # If validate endpoint not available, proceed to upload
            pass
        self._status("Saving configuration to slskd...")
        def worker():
            try:
                ok = self.service.options_upload_yaml(dumped)
                if ok:
                    # Trigger rescan and verify
                    self.service.shares_rescan()
                    # Give slskd a moment then fetch shares
                    import time
                    time.sleep(0.5)
                    shares_after = self.service.shares_list()
                else:
                    shares_after = {}
                wx.CallAfter(self._after_save, ok, shares_after, [it["path"] for it in items])
            except Exception as e:
                wx.CallAfter(self._after_error, f"Save failed: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def _after_save(self, ok: bool, shares_after: dict, intended_paths: list):
        if ok:
            # Compare intended vs actual
            actual = []
            try:
                for s in (shares_after.get("local") or []):
                    p = s.get("localPath") or s.get("raw") or s.get("remotePath")
                    if p:
                        actual.append(p)
            except Exception:
                pass
            missing = [p for p in intended_paths if p not in actual]
            if missing:
                wx.MessageBox(
                    "Configuration saved, but the following paths are not currently listed by slskd:\n\n"
                    + "\n".join(missing)
                    + "\n\nTry Options → Share Manager → Rescan Shares, or restart slskd.",
                    "Shares Pending",
                    wx.OK | wx.ICON_WARNING,
                    parent=self,
                )
            self._status("Configuration saved.")
            self.EndModal(wx.ID_OK)
        else:
            wx.MessageBox("slskd rejected the configuration.", "Save Failed", wx.OK | wx.ICON_ERROR, parent=self)

    def _after_error(self, msg: str):
        wx.MessageBox(msg, "Share Manager", wx.OK | wx.ICON_ERROR, parent=self)
        self._status(msg)

    # Helpers
    def _render_list(self, select_index: int = -1):
        self.lst.Freeze()
        try:
            self.lst.DeleteAllItems()
            for i, it in enumerate(self._share_items):
                alias = it.get("alias", "")
                path = it.get("path", "")
                self.lst.InsertItem(i, alias)
                self.lst.SetItem(i, 1, path)
            if 0 <= select_index < self.lst.GetItemCount():
                self.lst.SetItemState(select_index, wx.LIST_STATE_SELECTED, wx.LIST_STATE_SELECTED)
                self.lst.Focus(select_index)
        finally:
            self.lst.Thaw()
