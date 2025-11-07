import wx
from typing import Optional
from ..config import AppConfig


class SettingsDialog(wx.Dialog):
    def __init__(self, parent, cfg: AppConfig):
        super().__init__(parent, title="Settings", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._cfg = cfg

        pnl = wx.Panel(self)
        s = wx.GridBagSizer(6, 4)

        row = 0

        lblHost = wx.StaticText(pnl, label="Host (&H):")
        self.txtHost = wx.TextCtrl(pnl, value=cfg.host)
        self.txtHost.SetHint("http://localhost:5030")
        s.Add(lblHost, (row, 0), flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4)
        s.Add(self.txtHost, (row, 1), span=(1, 3), flag=wx.EXPAND)
        row += 1

        lblBase = wx.StaticText(pnl, label="URL Base (&B):")
        self.txtBase = wx.TextCtrl(pnl, value=cfg.url_base)
        self.txtBase.SetHint("/")
        s.Add(lblBase, (row, 0), flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4)
        s.Add(self.txtBase, (row, 1), span=(1, 3), flag=wx.EXPAND)
        row += 1

        self.chkVerify = wx.CheckBox(pnl, label="Verify SSL certificate (&V)")
        self.chkVerify.SetValue(bool(cfg.verify_ssl))
        s.Add(self.chkVerify, (row, 1), span=(1, 3))
        row += 1

        s.Add(wx.StaticLine(pnl), (row, 0), span=(1, 4), flag=wx.EXPAND | wx.TOP | wx.BOTTOM, border=6)
        row += 1

        # Credentials (username/password first for accessibility)
        lblUser = wx.StaticText(pnl, label="Username (&U):")
        self.txtUser = wx.TextCtrl(pnl, value=cfg.username)
        s.Add(lblUser, (row, 0), flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4)
        s.Add(self.txtUser, (row, 1), flag=wx.EXPAND)

        lblPass = wx.StaticText(pnl, label="Password (&P):")
        self.txtPass = wx.TextCtrl(pnl, value=cfg.password, style=wx.TE_PASSWORD)
        s.Add(lblPass, (row, 2), flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT | wx.LEFT, border=4)
        s.Add(self.txtPass, (row, 3), flag=wx.EXPAND)
        row += 1

        # Advanced credentials (API Key / Token) in a collapsible area
        self.advPane = wx.CollapsiblePane(pnl, label="&Advanced (API Key / Token)")
        s.Add(self.advPane, (row, 0), span=(1, 4), flag=wx.EXPAND)
        row += 1
        adv = self.advPane.GetPane()
        asz = wx.GridBagSizer(4, 2)
        arow = 0
        lblApiKey = wx.StaticText(adv, label="API Key (&K):")
        self.txtApiKey = wx.TextCtrl(adv, value=cfg.api_key, style=wx.TE_PASSWORD)
        asz.Add(lblApiKey, (arow, 0), flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4)
        asz.Add(self.txtApiKey, (arow, 1), flag=wx.EXPAND)
        arow += 1
        lblToken = wx.StaticText(adv, label="Token (&T):")
        self.txtToken = wx.TextCtrl(adv, value=cfg.token, style=wx.TE_PASSWORD)
        asz.Add(lblToken, (arow, 0), flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4)
        asz.Add(self.txtToken, (arow, 1), flag=wx.EXPAND)
        asz.AddGrowableCol(1, 1)
        adv.SetSizer(asz)

        lblTimeout = wx.StaticText(pnl, label="Timeout seconds (&S):")
        self.txtTimeout = wx.TextCtrl(pnl, value=str(cfg.timeout_s or 15.0))
        s.Add(lblTimeout, (row, 0), flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4)
        s.Add(self.txtTimeout, (row, 1), flag=wx.EXPAND)
        row += 1

        s.AddGrowableCol(1)
        s.AddGrowableCol(3)

        pnl.SetSizerAndFit(s)

        # Buttons: Test Login, OK, Cancel
        btns = wx.StdDialogButtonSizer()
        self.btnTest = wx.Button(self, wx.ID_ANY, "&Test Login")
        self.btnOk = wx.Button(self, wx.ID_OK)
        self.btnCancel = wx.Button(self, wx.ID_CANCEL)
        btns.AddButton(self.btnTest)
        btns.AddButton(self.btnOk)
        btns.AddButton(self.btnCancel)
        btns.Realize()

        tops = wx.BoxSizer(wx.VERTICAL)
        tops.Add(pnl, 1, wx.EXPAND | wx.ALL, 10)
        if btns:
            tops.Add(btns, 0, wx.EXPAND | wx.ALL, 10)
        self.SetSizerAndFit(tops)
        self.SetMinSize((520, 340))
        self.txtHost.SetFocus()

        self.Bind(wx.EVT_BUTTON, self.on_ok, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.on_test, self.btnTest)

    def on_ok(self, evt):
        try:
            timeout = float(self.txtTimeout.GetValue().strip() or "15")
        except ValueError:
            wx.MessageBox("Timeout must be a number.", "Invalid Input", wx.OK | wx.ICON_ERROR, parent=self)
            return
        host = self.txtHost.GetValue().strip()
        if not host:
            wx.MessageBox("Host is required.", "Missing Field", wx.OK | wx.ICON_ERROR, parent=self)
            return
        self._cfg.host = host
        self._cfg.url_base = self.txtBase.GetValue().strip() or "/"
        self._cfg.verify_ssl = bool(self.chkVerify.GetValue())
        self._cfg.api_key = self.txtApiKey.GetValue()
        self._cfg.token = self.txtToken.GetValue()
        self._cfg.username = self.txtUser.GetValue()
        self._cfg.password = self.txtPass.GetValue()
        self._cfg.timeout_s = timeout
        evt.Skip()

    @property
    def config(self) -> AppConfig:
        return self._cfg

    def on_test(self, evt):
        # Try connecting with form values (prefer username/password)
        test_cfg = AppConfig(
            host=self.txtHost.GetValue().strip() or "http://localhost:5030",
            url_base=self.txtBase.GetValue().strip() or "/",
            verify_ssl=bool(self.chkVerify.GetValue()),
            api_key=self.txtApiKey.GetValue(),
            token=self.txtToken.GetValue(),
            username=self.txtUser.GetValue(),
            password=self.txtPass.GetValue(),
            timeout_s=float(self.txtTimeout.GetValue().strip() or "15"),
        )
        from ..slsk_client import SlskService, SlskServiceError
        svc = SlskService(test_cfg)
        try:
            svc.connect()
            st = svc.app_state()
            ver = st.get("version", {}).get("full", "")
            wx.MessageBox(f"Login successful. slskd {ver}", "Success", wx.OK | wx.ICON_INFORMATION, parent=self)
        except SlskServiceError as e:
            wx.MessageBox(f"Login failed.\n{e}", "Authentication Error", wx.OK | wx.ICON_ERROR, parent=self)
