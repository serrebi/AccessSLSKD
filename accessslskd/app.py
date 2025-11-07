from __future__ import annotations

import argparse
import sys
import wx

from .config import load_config, reset_config, save_config
from .ui.main_frame import MainFrame


def main(argv=None):
    parser = argparse.ArgumentParser(prog="accessslskd", add_help=True)
    parser.add_argument("--config-reset", action="store_true", help="Reset saved configuration and exit.")
    args = parser.parse_args(argv or sys.argv[1:])

    if args.config_reset:
        reset_config()
        print("Configuration reset.")
        return 0

    cfg = load_config()
    app = wx.App()
    frame = MainFrame(cfg)
    frame.Show()
    app.MainLoop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

