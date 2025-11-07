accessslskd — Accessible wxPython client for slskd

Overview
- This is a vibe coded SLSKD client, mostly made for blind people to use.
- Designed to work with NVDA screen reader by using standard wx controls.
- I was sick of waiting for a client like Nicotine+ to become more accessible. In the meantime this slskd remote client might  be a pretty good fill in for people like me. It can search and download files and folders, filter file types for your searches, and you can manage your download directory, and shared folders from access SLSKD.

Prerequisites
- Python 3.10+ on Windows.
- slskd running and reachable (e.g., http://localhost:5030).
- API key, token, or username/password configured in slskd.
- Packages: wxPython, requests (pulled by slskd-api), slskd-api.

Install deps (if needed)
  pip install -r requirements.txt

Run
- Easiest: double-click start_accessslskd.bat
- Or from a terminal:
    python -m accessslskd
  Optional:
    python -m accessslskd --config-reset   # clear cached config

Portable Mode (Windows EXE)
- Portable builds store `config.json` next to the executable.
- When running from source, you can force portable mode by either:
  - setting `ACCESS_SLSKD_PORTABLE=1` in the environment, or
  - placing an empty file named `.portable` in your current working directory.

Build a Portable EXE (Windows)
- Requirements: Python 3.10+, pip, and a working C++ build toolchain if needed by wxPython.
- Quick build:
    ./build_portable.bat
  This produces `dist\accessslskd.exe`. On first run, a `config.json` will be written next to the EXE.
  Notes:
  - The build uses PyInstaller `--onefile --windowed` and collects `slskd_api` automatically.
  - If you want a console for debug, remove `--windowed` in the batch file.

First Run
- Use your Soulseek username and password (recommended).
- A Settings dialog prompts for Host (e.g., http://localhost:5030), URL Base (/), and credentials.
- Advanced (optional): API Key or Token if you already have one.
- Check "Verify SSL" only if using HTTPS with a valid certificate.

Notes on Accessibility
- All controls have labels and accelerators.
- Lists use wx.ListCtrl in report mode for NVDA compatibility.
- No custom drawn widgets; focus order follows tab order, with meaningful default focus.
- Status messages are announced via window title updates and status bar text.

Troubleshooting
- If Search returns no results, ensure your slskd is connected/logged in and that the API key has readwrite permissions.
- If you don’t know the API details, just enter your Soulseek username and password and use “Test Login” in Settings.
- For SSL issues, uncheck “Verify SSL” if using self-signed certs.
