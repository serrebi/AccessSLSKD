from __future__ import annotations

import wx
from typing import Callable

from ..config import AppConfig, save_config, load_config
from ..slsk_client import SlskService, SlskServiceError
from .settings_dialog import SettingsDialog
from .search_panel import SearchPanel
from .transfers_panel import TransfersPanel
from .rooms_panel import RoomsPanel
from .pm_panel import PmPanel


class MainFrame(wx.Frame):
    def __init__(self, cfg: AppConfig):
        super().__init__(None, title="accessslskd", size=(980, 700))
        self.cfg = cfg
        self.service = SlskService(cfg)

        self.statusbar = self.CreateStatusBar(2)
        self.statusbar.SetStatusWidths([-3, -1])
        self._build_menu()
        self._build_body()
        self.Centre()

        self.Bind(wx.EVT_CLOSE, self._on_close)

        # Attempt initial connection
        self._try_connect_first_run()

    def _build_menu(self):
        menubar = wx.MenuBar()

        mFile = wx.Menu()
        miSettings = mFile.Append(wx.ID_PREFERENCES, "&Settings\tCtrl+,")
        miLogin = mFile.Append(wx.ID_ANY, "&Login Now\tCtrl+L")
        miExit = mFile.Append(wx.ID_EXIT, "E&xit\tAlt+F4")
        menubar.Append(mFile, "&File")

        mOptions = wx.Menu()
        self.miSearchAuto = mOptions.AppendCheckItem(wx.ID_ANY, "Search Auto &Update")
        self.miSearchInterval = mOptions.Append(wx.ID_ANY, "Search &Interval…")
        mOptions.AppendSeparator()
        self.miTransfersAuto = mOptions.AppendCheckItem(wx.ID_ANY, "Transfers Auto &Refresh")
        self.miTransfersInterval = mOptions.Append(wx.ID_ANY, "Transfers &Interval…")
        mOptions.AppendSeparator()
        self.miShareMgr = mOptions.Append(wx.ID_ANY, "&Share Manager…")
        self.miSetDownloads = mOptions.Append(wx.ID_ANY, "Set &Downloads Folder…")
        menubar.Append(mOptions, "&Options")

        mHelp = wx.Menu()
        miDebug = mHelp.Append(wx.ID_ANY, "Copy &Debug Info")
        menubar.Append(mHelp, "&Help")

        self.SetMenuBar(menubar)

        self.Bind(wx.EVT_MENU, self._on_settings, miSettings)
        self.Bind(wx.EVT_MENU, self._on_login_now, miLogin)
        self.Bind(wx.EVT_MENU, lambda e: self.Close(), miExit)
        self.Bind(wx.EVT_MENU, self._on_copy_debug, miDebug)

        # Initialize options check states
        self.miSearchAuto.Check(self.cfg.search_auto_update)
        self.miTransfersAuto.Check(self.cfg.transfers_auto_update)
        # Wire options events
        self.Bind(wx.EVT_MENU, self._on_toggle_search_auto, self.miSearchAuto)
        self.Bind(wx.EVT_MENU, self._on_set_search_interval, self.miSearchInterval)
        self.Bind(wx.EVT_MENU, self._on_toggle_transfers_auto, self.miTransfersAuto)
        self.Bind(wx.EVT_MENU, self._on_set_transfers_interval, self.miTransfersInterval)
        self.Bind(wx.EVT_MENU, self._on_share_manager, self.miShareMgr)
        self.Bind(wx.EVT_MENU, self._on_set_downloads_folder, self.miSetDownloads)

    def _build_body(self):
        nb = wx.Notebook(self)
        self.nb = nb
        self.search_panel = SearchPanel(
            nb, self.service, self._set_status,
            auto_update=self.cfg.search_auto_update,
            interval_sec=self.cfg.search_interval_sec,
            search_timeout_ms=getattr(self.cfg, "search_timeout_ms", 120000),
        )
        self.transfers_panel = TransfersPanel(
            nb, self.service, self._set_status,
            auto_update=self.cfg.transfers_auto_update,
            interval_sec=self.cfg.transfers_interval_sec,
        )
        self.rooms_panel = RoomsPanel(nb, self.service, self._set_status)
        self.pm_panel = PmPanel(nb, self.service, self._set_status)
        nb.AddPage(self.search_panel, "&Search")
        nb.AddPage(self.transfers_panel, "&Transfers")
        nb.AddPage(self.rooms_panel, "&Rooms")
        nb.AddPage(self.pm_panel, "&PM")

        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(nb, 1, wx.EXPAND)
        self.SetSizer(s)
        # Auto-load available rooms when Rooms tab is shown
        self.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self._on_nb_changed, nb)

    # Status helpers
    def _set_status(self, msg: str, right: str = ""):
        self.statusbar.SetStatusText(msg or "", 0)
        if right is not None:
            self.statusbar.SetStatusText(right or "", 1)
        if msg:
            self.SetTitle(f"accessslskd — {msg}")

    # Events
    def _on_settings(self, evt):
        dlg = SettingsDialog(self, self.cfg)
        if dlg.ShowModal() == wx.ID_OK:
            save_config(dlg.config)
            self.cfg = dlg.config
            self.service = SlskService(self.cfg)
            self._connect_with_feedback()
        dlg.Destroy()

    def _on_copy_debug(self, evt):
        info = self.cfg.sanitized()
        info_text = "Config (sanitized):\n" + "\n".join(f"- {k}: {v}" for k, v in info.items())
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(info_text))
            wx.TheClipboard.Close()
        self._set_status("Debug info copied to clipboard.")

    def _try_connect_first_run(self):
        # Show settings if no creds
        if not (self.cfg.api_key or self.cfg.token or (self.cfg.username and self.cfg.password)):
            self._set_status("Configure connection settings.")
            self._on_settings(None)
        else:
            self._connect_with_feedback()

    def _connect_with_feedback(self):
        try:
            self._set_status("Connecting to slskd...")
            self.service.connect()
            state = self.service.app_state()
            ver = state.get("version", {}).get("full", "")
            self._set_status(f"Connected. slskd {ver}")
        except SlskServiceError as e:
            wx.MessageBox(f"Connection failed:\n{e}", "Connection Error", wx.OK | wx.ICON_ERROR, parent=self)
            self._set_status("Not connected.")

    def _on_login_now(self, evt):
        self._connect_with_feedback()

    def _on_close(self, evt):
        try:
            # Stop rooms auto-refresh timer if running
            if hasattr(self, "rooms_panel") and hasattr(self.rooms_panel, "on_activated"):
                self.rooms_panel.on_activated(False)
        except Exception:
            pass
        self.Destroy()
    def _on_nb_changed(self, evt):
        try:
            new_idx = evt.GetSelection()
            page = self.nb.GetPage(new_idx)
            self.rooms_panel.on_activated(page is self.rooms_panel)
        except Exception:
            pass
        evt.Skip()

    # Options handlers
    def _on_toggle_search_auto(self, evt):
        val = self.miSearchAuto.IsChecked()
        self.cfg.search_auto_update = bool(val)
        save_config(self.cfg)
        self.search_panel.set_auto_update(val)
        self._set_status(f"Search Auto Update {'On' if val else 'Off'}")

    def _on_set_search_interval(self, evt):
        val = wx.GetNumberFromUser("Seconds between search updates:", "Seconds:", "Search Interval", self.cfg.search_interval_sec, 1, 120, self)
        if val == -1:
            return
        self.cfg.search_interval_sec = int(val)
        save_config(self.cfg)
        self.search_panel.set_interval(self.cfg.search_interval_sec)
        self._set_status(f"Search interval {self.cfg.search_interval_sec}s")

    def _on_toggle_transfers_auto(self, evt):
        val = self.miTransfersAuto.IsChecked()
        self.cfg.transfers_auto_update = bool(val)
        save_config(self.cfg)
        self.transfers_panel.set_auto_update(val)
        self._set_status(f"Transfers Auto Refresh {'On' if val else 'Off'}")

    def _on_set_transfers_interval(self, evt):
        val = wx.GetNumberFromUser("Seconds between transfer updates:", "Seconds:", "Transfers Interval", self.cfg.transfers_interval_sec, 1, 300, self)
        if val == -1:
            return
        self.cfg.transfers_interval_sec = int(val)
        save_config(self.cfg)
        self.transfers_panel.set_interval(self.cfg.transfers_interval_sec)
        self._set_status(f"Transfers interval {self.cfg.transfers_interval_sec}s")

    def _on_share_manager(self, evt):
        from .share_manager import ShareManagerDialog
        dlg = ShareManagerDialog(self, self.service)
        dlg.ShowModal()
        dlg.Destroy()

    def _on_set_downloads_folder(self, evt):
        # Pull current YAML to prefill
        try:
            yml = self.service.options_download_yaml()
        except Exception as e:
            wx.MessageBox(f"Unable to fetch configuration from slskd.\n\n{e}", "Options", wx.OK | wx.ICON_ERROR, parent=self)
            return
        downloads = ""
        yaml_mod = None
        try:
            import yaml as _yaml  # type: ignore
            yaml_mod = _yaml
            obj = _yaml.safe_load(yml) or {}
            downloads = str(((obj.get("directories") or {}).get("downloads") or "")) if isinstance(obj, dict) else ""
        except Exception:
            obj = {}
        # Ask for folder
        with wx.DirDialog(self, "Choose Downloads Folder", defaultPath=downloads or "") as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            new_path = dlg.GetPath()
        if not yaml_mod:
            wx.MessageBox("PyYAML is required to save this setting.\n\nInstall with:\n  python -m pip install PyYAML", "Missing Dependency", wx.OK | wx.ICON_WARNING, parent=self)
            return
        # Update YAML and save
        try:
            if not isinstance(obj, dict):
                obj = {}
            dirs = dict(obj.get("directories") or {})
            dirs["downloads"] = new_path
            obj["directories"] = dirs
            dumped = yaml_mod.safe_dump(obj, sort_keys=False, allow_unicode=True)
            ok = self.service.options_upload_yaml(dumped)
            if ok:
                self._set_status(f"Downloads folder set to {new_path}")
            else:
                wx.MessageBox("slskd rejected the configuration.", "Save Failed", wx.OK | wx.ICON_ERROR, parent=self)
        except Exception as e:
            wx.MessageBox(f"Failed to save configuration.\n\n{e}", "Save Failed", wx.OK | wx.ICON_ERROR, parent=self)
