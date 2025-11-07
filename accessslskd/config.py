import json
import os
import sys
import threading
from dataclasses import dataclass, asdict
from typing import Optional

APP_DIR_NAME = "accessslskd"
CONFIG_FILE_NAME = "config.json"


def _portable_base_dir() -> Optional[str]:
    """
    Returns a directory for portable mode if enabled.
    Rules:
    - If running as a frozen executable (PyInstaller), always use the executable's directory.
    - Else, if env ACCESS_SLSKD_PORTABLE is set to 1/true/yes, use current working directory.
    - Else, if a '.portable' file or an existing 'config.json' sits in CWD, use CWD.
    """
    try:
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
    except Exception:
        pass
    try:
        cwd = os.getcwd()
    except Exception:
        cwd = os.path.expanduser("~")
    if str(os.environ.get("ACCESS_SLSKD_PORTABLE", "")).strip().lower() in ("1", "true", "yes"):
        return cwd
    if os.path.exists(os.path.join(cwd, ".portable")) or os.path.exists(os.path.join(cwd, CONFIG_FILE_NAME)):
        return cwd
    return None


def _app_config_dir() -> str:
    # Portable mode?
    pdir = _portable_base_dir()
    if pdir:
        os.makedirs(pdir, exist_ok=True)
        return pdir
    # Default: Prefer APPDATA on Windows; fall back to user home
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def _config_path() -> str:
    return os.path.join(_app_config_dir(), CONFIG_FILE_NAME)


@dataclass
class AppConfig:
    host: str = "http://localhost:5030"
    url_base: str = "/"
    api_key: str = ""
    token: str = ""
    username: str = ""
    password: str = ""
    verify_ssl: bool = False
    timeout_s: float = 15.0
    # UI / Auto update options
    search_auto_update: bool = True
    search_interval_sec: int = 2
    # How long a server-side search should run before slskd stops it (ms)
    # Minimum enforced at 30 minutes to avoid premature timeouts.
    search_timeout_ms: int = 1800000
    transfers_auto_update: bool = True
    transfers_interval_sec: int = 5

    def sanitized(self) -> dict:
        d = asdict(self)
        # Omit secrets for logging
        d_s = dict(d)
        d_s.pop("api_key", None)
        d_s.pop("token", None)
        d_s.pop("password", None)
        return d_s


_lock = threading.Lock()


def load_config() -> AppConfig:
    path = _config_path()
    if not os.path.exists(path):
        return AppConfig()
    with _lock, open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return AppConfig(**{**asdict(AppConfig()), **data})


def save_config(cfg: AppConfig) -> None:
    path = _config_path()
    with _lock, open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(cfg), f, indent=2)


def reset_config() -> None:
    path = _config_path()
    if os.path.exists(path):
        os.remove(path)
