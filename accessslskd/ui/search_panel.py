from __future__ import annotations

import threading
import time
from typing import List, Dict, Any, Optional, Set

import wx
from slskd_api.apis._types import SearchResponseItem, SearchState

from ..slsk_client import SlskService


class SearchPanel(wx.Panel):
    def __init__(self, parent, service: SlskService, on_status, *, auto_update: bool = True, interval_sec: int = 2, search_timeout_ms: int = 1800000):
        super().__init__(parent)
        self.service = service
        self.on_status = on_status
        self.current_search_id = None
        self._flat_rows: List[Dict[str, Any]] = []
        self._auto_enabled = bool(auto_update)
        self._interval_sec = max(1, int(interval_sec))
        # Enforce a minimum 30-minute timeout for server-side searches
        try:
            self._search_timeout_ms = int(search_timeout_ms or 0)
        except Exception:
            self._search_timeout_ms = 0
        if self._search_timeout_ms <= 0 or self._search_timeout_ms < 30 * 60 * 1000:
            self._search_timeout_ms = 30 * 60 * 1000
        # Perf / concurrency guards
        self._fetch_in_progress = False
        self._prev_keys: List[tuple] = []
        self._building_ui()
        self._build_context_menu()
        # Auto update timer for search results
        self._timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_timer, self._timer)

    def _building_ui(self):
        tops = wx.BoxSizer(wx.VERTICAL)
        # Query row
        qrow = wx.BoxSizer(wx.HORIZONTAL)
        self.lblQuery = wx.StaticText(self, label="Query (&Q):")
        self.txtQuery = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        # Search type selector
        self.lblType = wx.StaticText(self, label="Type (&T):")
        self.choiceType = wx.Choice(
            self,
            choices=[
                "All",
                "Audio",
                "Videos",
                "Software",
                "Books",
                "Photos",
                "Archives",
            ],
        )
        self.choiceType.SetSelection(0)
        self.btnSearch = wx.Button(self, wx.ID_ANY, "&Search")
        self.btnRefresh = wx.Button(self, wx.ID_ANY, "&Refresh Results")
        qrow.Add(self.lblQuery, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        qrow.Add(self.txtQuery, 1, wx.RIGHT, 6)
        qrow.Add(self.lblType, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        qrow.Add(self.choiceType, 0, wx.RIGHT, 6)
        qrow.Add(self.btnSearch, 0, wx.RIGHT, 6)
        qrow.Add(self.btnRefresh, 0)
        tops.Add(qrow, 0, wx.EXPAND | wx.ALL, 8)

        # Single flat files list as one textual line per row for NVDA
        self.lstFiles = wx.ListCtrl(self, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        self.lstFiles.InsertColumn(0, "Result", width=1100)
        tops.Add(self.lstFiles, 1, wx.EXPAND | wx.ALL, 8)

        # Actions row
        arow = wx.BoxSizer(wx.HORIZONTAL)
        self.btnEnqueueSel = wx.Button(self, wx.ID_ANY, "Enqueue &Selected File(s)")
        self.btnEnqueueAll = wx.Button(self, wx.ID_ANY, "Enqueue &All From Same User")
        arow.Add(self.btnEnqueueSel, 0, wx.RIGHT, 8)
        arow.Add(self.btnEnqueueAll, 0)
        tops.Add(arow, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        self.SetSizer(tops)

        # Events
        self.Bind(wx.EVT_BUTTON, self._on_search, self.btnSearch)
        self.Bind(wx.EVT_TEXT_ENTER, self._on_search, self.txtQuery)
        self.Bind(wx.EVT_BUTTON, self._on_refresh, self.btnRefresh)
        self.Bind(wx.EVT_BUTTON, self._on_enqueue_selected, self.btnEnqueueSel)
        self.Bind(wx.EVT_BUTTON, self._on_enqueue_all, self.btnEnqueueAll)
        self.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK, self._on_right_click, self.lstFiles)
        self.Bind(wx.EVT_CONTEXT_MENU, self._on_context_menu)
        self.Bind(wx.EVT_CHOICE, lambda e: self._with_status(f"Type: {self.choiceType.GetStringSelection()}"), self.choiceType)

    # Helpers
    def _with_status(self, msg: str):
        if callable(self.on_status):
            self.on_status(msg)

    def _clear_list(self):
        self.lstFiles.DeleteAllItems()
        self._flat_rows = []

    def _selected_type_exts(self) -> Optional[Set[str]]:
        kind = (self.choiceType.GetStringSelection() or "All").lower()
        if kind == "all":
            return None
        groups: Dict[str, Set[str]] = {
            "audio": {
                # Core
                ".mp3", ".ogg", ".opus", ".flac", ".wav", ".aac", ".m4a", ".wma", ".alac",
                # Popular/hi‑res and containers
                ".ape", ".aiff", ".aif", ".aifc", ".mka", ".wv", ".tta", ".mpc", ".ra", ".ram", ".oga",
                # Surround/codecs
                ".ac3", ".dts",
                # MIDI and trackers
                ".mid", ".midi", ".kar", ".mod", ".xm", ".it", ".s3m",
                # Voice/telephony and misc
                ".amr", ".caf", ".spx", ".mp2", ".mp1",
                # DSD
                ".dsf", ".dff",
                # Multi‑track Ogg
                ".mogg",
            },
            "videos": {
                # Core
                ".avi", ".mp4", ".mkv", ".mov", ".wmv", ".flv", ".webm",
                # MPEG family
                ".mpg", ".mpeg", ".mpe", ".m1v", ".m2v", ".m4v",
                # Mobile/cam
                ".3gp", ".3g2", ".ts", ".m2ts", ".mts", ".vob",
                # Alt containers/codecs
                ".ogv", ".ogm", ".divx", ".rm", ".rmvb", ".asf", ".f4v", ".mxf", ".dv", ".qt",
                # Broadcast/recordings
                ".wtv", ".dvr-ms", ".trp", ".tp", ".tod",
                # Elementary streams
                ".h264", ".h265", ".hevc", ".av1", ".y4m",
                # Matroska variants
                ".mk3d",
            },
            "software": {
                # Windows installers/packages
                ".exe", ".msi", ".msix", ".msixbundle", ".appx", ".appxbundle", ".msu", ".cab",
                # macOS
                ".dmg", ".pkg", ".mpkg", ".app", ".kext", ".saver",
                # Linux/BSD packages and installers
                ".deb", ".rpm", ".apk", ".appimage", ".snap", ".flatpak", ".flatpakref", ".flatpakrepo",
                ".run", ".bin", ".sh",
                # Arch/Manjaro package formats
                ".pkg.tar.zst", ".pkg.tar.xz", ".pkg.tar.gz",
                # Images commonly used for software distribution
                ".iso", ".img",
            },
            "books": {
                ".pdf", ".epub", ".mobi", ".azw", ".azw3", ".djvu", ".cbz", ".cbr",
                ".txt", ".rtf", ".doc", ".docx", ".odt",
            },
            "photos": {
                ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp",
                ".heic", ".heif", ".raw", ".cr2", ".nef", ".arw", ".orf", ".rw2", ".sr2",
            },
            "archives": {
                # Common
                ".7z", ".rar", ".zip", ".zipx", ".tar",
                # Compressed tars
                ".tgz", ".tbz", ".tbz2", ".txz", ".tzst",
                # Single‑stream compressions
                ".gz", ".bz2", ".xz", ".zst", ".lz", ".lzma", ".lz4", ".z", ".Z",
                # Others / legacy
                ".cab", ".arj", ".ace", ".arc", ".lha", ".lzh", ".sit", ".sitx", ".pax",
                # Game/engine archives
                ".pak", ".pk3", ".pk4", ".wad",
                # Disc images (often used as archives)
                ".iso", ".img", ".nrg", ".bin", ".cue", ".mdf", ".mds", ".ccd", ".isz", ".dmg",
                # Comic book archives
                ".cbz", ".cbr", ".cb7", ".cbt",
            },
        }
        return groups.get(kind, None)

    def _matches_type(self, filename: str) -> bool:
        exts = self._selected_type_exts()
        if not exts:
            return True
        name = (filename or "").lower()
        for ext in exts:
            if name.endswith(ext):
                return True
        return False

    def _flatten_responses(self, responses: List[SearchResponseItem]) -> List[Dict[str, Any]]:
        flat: List[Dict[str, Any]] = []
        for r in responses or []:
            user = r.get("username", "")
            queue = int(r.get("queueLength", 0))
            speed = int(r.get("uploadSpeed", 0))
            slot = bool(r.get("hasFreeUploadSlot"))
            regular = list(r.get("files") or [])
            locked = list(r.get("lockedFiles") or [])
            # Mark locked files so the UI can display it
            locked = [dict(f, **{"isLocked": True}) if isinstance(f, dict) else f for f in locked]
            for f in (regular + locked):
                if self._matches_type(str((f or {}).get("filename", "") or "")):
                    flat.append(dict(
                        username=user,
                        queueLength=queue,
                        uploadSpeed=speed,
                        hasFreeUploadSlot=slot,
                        file=f or {},
                    ))
        return flat

    def _format_row_text(self, row: Dict[str, Any]) -> str:
        f = row.get("file", {}) or {}
        full = str(f.get("filename", "") or "")
        # Derive folder and basename using last backslash or slash
        sep_pos = max(full.rfind("\\"), full.rfind("/"))
        folder = full[:sep_pos + 1] if sep_pos >= 0 else ""
        name_only = full[sep_pos + 1 :] if sep_pos >= 0 else full
        parts = [
            f"{name_only}",
            f"Size: {f.get('size', '')}",
            f"User: {row.get('username','')}",
            f"Queue: {row.get('queueLength', '')}",
            f"Slot Free: {'Yes' if row.get('hasFreeUploadSlot') else 'No'}",
            f"Speed: {row.get('uploadSpeed','')}",
        ]
        # Optional/known fields in the requested order
        if f.get("length") is not None:
            parts.append(f"Length(s): {f.get('length')}")
        if f.get("bitRate") is not None:
            parts.append(f"Bitrate: {f.get('bitRate')}")
        if f.get("bitDepth") is not None:
            parts.append(f"BitDepth: {f.get('bitDepth')}")
        if f.get("sampleRate") is not None:
            parts.append(f"SampleRate: {f.get('sampleRate')}")
        parts.append(f"Locked: {'Yes' if f.get('isLocked') else 'No'}")
        # Include folder at the end for reference
        if folder:
            parts.append(f"Folder: {folder}")
        return "; ".join(parts)

    def _populate_flat(self, flat_rows: List[Dict[str, Any]]):
        self.lstFiles.Freeze()
        try:
            self.lstFiles.DeleteAllItems()
            for row in flat_rows:
                text = self._format_row_text(row)
                self.lstFiles.InsertItem(self.lstFiles.GetItemCount(), text)
        finally:
            self.lstFiles.Thaw()
        self._flat_rows = flat_rows

    # Event handlers
    def _on_search(self, evt):
        query = self.txtQuery.GetValue().strip()
        if not query:
            self._with_status("Enter a search query.")
            return
        self.btnSearch.Disable()
        self.btnRefresh.Disable()
        sel_type = self.choiceType.GetStringSelection() or "All"
        self._with_status(f"Searching ({sel_type})…")

        def worker():
            try:
                res = self.service.start_search(query, timeout_ms=getattr(self, "_search_timeout_ms", 0) or None)
                self.current_search_id = res.id
                wx.CallAfter(self._after_new_search_started, res.id)
            except Exception as e:
                wx.CallAfter(self._after_error, f"Search failed: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def _after_new_search_started(self, search_id: str):
        # Clear old results and start polling immediately; keep polling indefinitely
        self._clear_list()
        self._fetch_once()
        self.btnSearch.Enable(True)
        self.btnRefresh.Enable(True)
        self._arm_timer()

    def _on_refresh(self, evt):
        if not self.current_search_id:
            self._with_status("Nothing to refresh. Run a search first.")
            return
        self.btnRefresh.Disable()

        self._fetch_once()

    def _after_refresh(self, flat_rows: List[Dict[str, Any]], state: SearchState):
        self._populate_flat(flat_rows)
        self.btnRefresh.Enable(True)
        self._with_status(f"Updated — {len(flat_rows)} files.")

    def _selected_file_rows(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        i = -1
        while True:
            i = self.lstFiles.GetNextItem(i, wx.LIST_NEXT_ALL, wx.LIST_STATE_SELECTED)
            if i == -1:
                break
            if 0 <= i < len(self._flat_rows):
                rows.append(self._flat_rows[i])
        return rows

    def _on_enqueue_selected(self, evt):
        rows = self._selected_file_rows()
        if not rows:
            self._with_status("Select one or more files to enqueue.")
            return
        # Group by user, enqueue per user
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for r in rows:
            user = r.get("username", "")
            f = r.get("file", {})
            grouped.setdefault(user, []).append({"filename": f.get("filename", ""), "size": int(f.get("size", 0))})
        self._enqueue_grouped(grouped)

    def _on_enqueue_all(self, evt):
        # Take the first selected row's user, enqueue all files in the list for that user
        rows = self._selected_file_rows()
        if not rows:
            self._with_status("Select a file so I know which user.")
            return
        user = rows[0].get("username", "")
        files = []
        for r in self._flat_rows:
            if r.get("username", "") == user:
                f = r.get("file", {})
                files.append({"filename": f.get("filename", ""), "size": int(f.get("size", 0))})
        self._enqueue_grouped({user: files})

    def _enqueue_grouped(self, grouped: Dict[str, List[Dict[str, Any]]]):
        total = sum(len(v) for v in grouped.values())
        self._with_status(f"Enqueueing {total} file(s) from {len(grouped)} user(s)...")

        def worker():
            try:
                failures = 0
                for user, files in grouped.items():
                    if files:
                        ok = self.service.enqueue_downloads(user, files)
                        if not ok:
                            failures += len(files)
                msg = f"Enqueued {total - failures}/{total} file(s)."
                wx.CallAfter(self._with_status, msg)
            except Exception as e:
                wx.CallAfter(self._after_error, f"Enqueue failed: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def _after_error(self, msg: str):
        self.btnSearch.Enable(True)
        self.btnRefresh.Enable(True)
        self._with_status(msg)
        wx.Bell()

    # Context menu
    def _build_context_menu(self):
        self._menu = wx.Menu()
        self._miDownload = self._menu.Append(wx.ID_ANY, "Download &File(s)")
        self._miDownloadDir = self._menu.Append(wx.ID_ANY, "Download Containing &Directory")
        self._menu.AppendSeparator()
        self._miEnqueueAllUser = self._menu.Append(wx.ID_ANY, "Enqueue &All From Same User")
        self._menu.AppendSeparator()
        self._miBrowseUser = self._menu.Append(wx.ID_ANY, "&Browse User…")
        self.Bind(wx.EVT_MENU, lambda e: self._on_enqueue_selected(e), self._miDownload)
        self.Bind(wx.EVT_MENU, self._on_download_dir, self._miDownloadDir)
        self.Bind(wx.EVT_MENU, self._on_enqueue_all, self._miEnqueueAllUser)
        self.Bind(wx.EVT_MENU, self._on_browse_user, self._miBrowseUser)

    def _on_right_click(self, evt):
        self.PopupMenu(self._menu)

    def _on_context_menu(self, evt):
        # Keyboard context menu key
        self.PopupMenu(self._menu)

    def _on_download_dir(self, evt):
        rows = self._selected_file_rows()
        if not rows:
            self._with_status("Select a file first.")
            return
        # Take first selected
        r = rows[0]
        user = r.get("username", "")
        f = r.get("file", {}) or {}
        full = str(f.get("filename", "") or "")
        sep_pos = max(full.rfind("\\"), full.rfind("/"))
        directory = full[:sep_pos] if sep_pos >= 0 else ""
        if not directory:
            self._with_status("Could not determine containing directory.")
            return
        self._with_status(f"Enqueueing directory for {user}: {directory} …")

        def worker():
            try:
                count = self.service.enqueue_directory(user, directory)
                wx.CallAfter(self._with_status, f"Enqueued {count} file(s) from directory.")
            except Exception as e:
                wx.CallAfter(self._after_error, f"Download directory failed: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def _on_browse_user(self, evt):
        rows = self._selected_file_rows()
        if not rows:
            self._with_status("Select a result first.")
            return
        user = rows[0].get("username", "")
        from .user_browser import UserBrowserFrame
        frame = UserBrowserFrame(self.GetTopLevelParent(), self.service, user, self._with_status)
        frame.Show()

    # Auto update/polling
    def _on_toggle_auto(self, evt):
        self._arm_timer()

    def _on_change_interval(self, evt):
        self._arm_timer()

    def _arm_timer(self):
        self._timer.Stop()
        if self._auto_enabled and self.current_search_id:
            interval_ms = max(1, int(self._interval_sec)) * 1000
            self._timer.Start(interval_ms)

    def _on_timer(self, evt):
        if self.current_search_id and self._auto_enabled and not self._fetch_in_progress:
            self._fetch_once()

    def _fetch_once(self):
        sid = self.current_search_id
        if not sid:
            return
        if self._fetch_in_progress:
            return
        self._fetch_in_progress = True
        def worker():
            try:
                t0 = time.perf_counter()
                # Fetch lightweight state first (no responses)
                state = self.service.get_search_state(sid, include_responses=False)
                t_state = (time.perf_counter() - t0) * 1000.0
                # Fetch responses via dedicated endpoint
                t1 = time.perf_counter()
                responses = self.service.get_search_responses(sid) or []
                t_resp = (time.perf_counter() - t1) * 1000.0
                t2 = time.perf_counter()
                flat = self._flatten_responses(responses)
                t_flat = (time.perf_counter() - t2) * 1000.0
                wx.CallAfter(self._after_fetch_once, flat, state, dict(ms_state=t_state, ms_resp=t_resp, ms_flat=t_flat))
            except Exception as e:
                wx.CallAfter(self._after_error, f"Update failed: {e}")
            finally:
                wx.CallAfter(self._mark_idle)
        threading.Thread(target=worker, daemon=True).start()

    def _mark_idle(self):
        self._fetch_in_progress = False

    def _after_fetch_once(self, flat_rows: List[Dict[str, Any]], state: SearchState, timings: Dict[str, float] | None = None):
        # Skip repaint if nothing changed (reduces CPU on big result sets)
        new_keys = [self._row_key(r) for r in flat_rows]
        repaint = new_keys != self._prev_keys
        # Preserve selection/scroll before potential repaint
        sel_keys = self._selected_keys()
        top_key = self._top_key()
        focus_key = self._focused_key()
        if repaint:
            self._populate_flat(flat_rows)
            self._prev_keys = new_keys
        # Status with light perf info
        ms_state = (timings or {}).get("ms_state", 0.0)
        ms_resp = (timings or {}).get("ms_resp", 0.0)
        ms_flat = (timings or {}).get("ms_flat", 0.0)
        right = f"{len(flat_rows)} files | net:{ms_state+ms_resp:.0f}ms ui:{ms_flat:.0f}ms"
        self._with_status(f"{'Updated' if repaint else 'No change'} — {len(flat_rows)} files. {right}")
        # Restore selection/scroll
        self._restore_selection(sel_keys, top_key, focus_key)
        # Keep polling indefinitely while Auto Update is enabled.
        # Controls stay enabled so you can start another search anytime.
        self.btnSearch.Enable(True)
        self.btnRefresh.Enable(True)

    # Selection/scroll preservation
    def _row_key(self, row: Dict[str, Any]):
        f = row.get("file", {}) or {}
        return (row.get("username",""), f.get("filename",""), int(f.get("size",0)))

    def _selected_keys(self):
        keys = set()
        i = -1
        while True:
            i = self.lstFiles.GetNextItem(i, wx.LIST_NEXT_ALL, wx.LIST_STATE_SELECTED)
            if i == -1:
                break
            if 0 <= i < len(self._flat_rows):
                keys.add(self._row_key(self._flat_rows[i]))
        return keys

    def _top_key(self):
        top = self.lstFiles.GetTopItem()
        if 0 <= top < len(self._flat_rows):
            return self._row_key(self._flat_rows[top])
        return None

    def _focused_key(self):
        # Focused row is where keyboard focus sits; preserve this across refreshes
        idx = self.lstFiles.GetNextItem(-1, wx.LIST_NEXT_ALL, wx.LIST_STATE_FOCUSED)
        if idx != -1 and 0 <= idx < len(self._flat_rows):
            return self._row_key(self._flat_rows[idx])
        # Fallback to first selected
        idx = self.lstFiles.GetNextItem(-1, wx.LIST_NEXT_ALL, wx.LIST_STATE_SELECTED)
        if idx != -1 and 0 <= idx < len(self._flat_rows):
            return self._row_key(self._flat_rows[idx])
        return None

    def _restore_selection(self, keys, top_key, focus_key=None):
        if keys:
            for i, r in enumerate(self._flat_rows):
                if self._row_key(r) in keys:
                    self.lstFiles.SetItemState(i, wx.LIST_STATE_SELECTED, wx.LIST_STATE_SELECTED)
        # Restore focused row first if available (keeps NVDA position), otherwise anchor to top_key
        if focus_key:
            for i, r in enumerate(self._flat_rows):
                if self._row_key(r) == focus_key:
                    self.lstFiles.Focus(i)
                    self.lstFiles.EnsureVisible(i)
                    break
        elif top_key:
            for i, r in enumerate(self._flat_rows):
                if self._row_key(r) == top_key:
                    self.lstFiles.EnsureVisible(i)
                    break
        # Ensure at least one focus/selection exists to avoid jumps
        if not keys and self.lstFiles.GetItemCount() > 0:
            self.lstFiles.SetItemState(0, wx.LIST_STATE_SELECTED, wx.LIST_STATE_SELECTED)
            self.lstFiles.Focus(0)
            self.lstFiles.EnsureVisible(0)

    # Options integration
    def set_auto_update(self, enabled: bool):
        self._auto_enabled = bool(enabled)
        self._arm_timer()

    def set_interval(self, seconds: int):
        self._interval_sec = max(1, int(seconds))
        self._arm_timer()

