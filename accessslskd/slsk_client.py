from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

# Try importing installed slskd_api; if missing, fall back to the user’s clone.
try:
    import slskd_api  # type: ignore
except ModuleNotFoundError:
    import sys, os
    _fallback = r"C:\Users\admin\slskd-python-api"
    if os.path.isdir(_fallback):
        sys.path.insert(0, _fallback)
        import slskd_api  # type: ignore
    else:
        raise
# (Optional debug removed; keep fallback import support)
# The public PyPI build of slskd_api may omit apis._types in some versions.
# Treat these as runtime-optional and use 'Any' stubs when missing.
from typing import Any as _Any, TYPE_CHECKING
try:
    if TYPE_CHECKING:
        from slskd_api.apis._types import (  # type: ignore
            Conversation,
            Directory,
            Event,
            Room,
            RoomInfo,
            RoomMessage,
            RoomUser,
            SearchResponseItem,
            SearchState,
            Transfer,
            UserRootDir,
        )
    else:
        raise ImportError
except Exception:
    Conversation = _Any  # type: ignore
    Directory = _Any  # type: ignore
    Event = _Any  # type: ignore
    Room = _Any  # type: ignore
    RoomInfo = _Any  # type: ignore
    RoomMessage = _Any  # type: ignore
    RoomUser = _Any  # type: ignore
    SearchResponseItem = _Any  # type: ignore
    SearchState = _Any  # type: ignore
    Transfer = _Any  # type: ignore
    UserRootDir = _Any  # type: ignore

from .config import AppConfig


class SlskServiceError(Exception):
    pass


@dataclass
class SearchResult:
    id: str
    state: SearchState


class SlskService:
    """
    Thin wrapper around slskd_api.SlskdClient with convenience methods and basic retries.
    """

    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        self._client = None
        self._lock = threading.RLock()

    def connect(self) -> None:
        with self._lock:
            if self._client:
                return
            kwargs = dict(
                host=self.cfg.host,
                url_base=self.cfg.url_base,
                verify_ssl=self.cfg.verify_ssl,
                timeout=self.cfg.timeout_s,
            )
            # Pick one auth method in order: api_key, token, username/password
            if self.cfg.api_key:
                kwargs["api_key"] = self.cfg.api_key
            elif self.cfg.token:
                kwargs["token"] = self.cfg.token
            elif self.cfg.username and self.cfg.password:
                kwargs["username"] = self.cfg.username
                kwargs["password"] = self.cfg.password
            else:
                raise SlskServiceError("No credentials provided. Configure API key, token, or username/password.")
            try:
                self._client = slskd_api.SlskdClient(**kwargs)
                # Sanity check connectivity
                _ = self._client.application.state()
            except Exception as e:
                self._client = None
                raise SlskServiceError(str(e)) from e

    # Application / status
    def app_state(self) -> dict:
        self._ensure()
        return self._client.application.state()

    # Searches
    def start_search(self, query: str, *, timeout_ms: Optional[int] = None) -> SearchResult:
        self._ensure()
        kwargs: Dict[str, int] = {}
        # Enforce a minimum of 30 minutes to avoid premature timeouts (works well with slskd).
        MIN_MS = 30 * 60 * 1000  # 1,800,000 ms
        MAX_MS = None
        try:
            # Prefer explicit override; else config; else default minimum.
            candidate = None
            if timeout_ms is not None:
                candidate = int(timeout_ms)
            elif getattr(self.cfg, "search_timeout_ms", None) is not None:
                candidate = int(self.cfg.search_timeout_ms)  # type: ignore[attr-defined]
            # If candidate is not provided or <= 0, force the minimum
            if not candidate or candidate <= 0:
                candidate = MIN_MS
            # Clamp to at least MIN_MS
            if candidate < MIN_MS:
                candidate = MIN_MS
            kwargs["searchTimeout"] = candidate
        except Exception:
            kwargs["searchTimeout"] = MIN_MS
        st = self._client.searches.search_text(query, **kwargs)
        return SearchResult(id=st["id"], state=st)

    def get_search_state(self, search_id: str, include_responses: bool = True) -> SearchState:
        self._ensure()
        return self._client.searches.state(search_id, includeResponses=include_responses)

    def get_search_responses(self, search_id: str) -> List[SearchResponseItem]:
        self._ensure()
        return self._client.searches.search_responses(search_id)

    def stop_search(self, search_id: str) -> bool:
        self._ensure()
        try:
            return bool(self._client.searches.stop(search_id))
        except Exception:
            return False

    def delete_search(self, search_id: str) -> bool:
        self._ensure()
        try:
            return bool(self._client.searches.delete(search_id))
        except Exception:
            return False

    # Transfers
    def enqueue_downloads(self, username: str, files: List[Dict[str, Any]]) -> bool:
        self._ensure()
        return self._client.transfers.enqueue(username, files)

    def browse_user_root(self, username: str):
        """Fetch user's root directory listing."""
        self._ensure()
        return self._client.users.browse(username)

    def user_directory(self, username: str, directory: str):
        """Fetch a specific directory for a user."""
        self._ensure()
        return self._client.users.directory(username, directory)

    def enqueue_directory(self, username: str, directory: str, limit: Optional[int] = None) -> int:
        """
        Enqueue all files from a remote directory (and subdirectories if returned).
        Returns count enqueued.
        """
        self._ensure()
        items = self.user_directory(username, directory) or []

        def iter_files(d):
            # Be tolerant to shapes: some servers may return nested 'directories'
            files = d.get("files") or []
            for f in files:
                # Build full remote path; if 'filename' already absolute, keep it
                name = f.get("filename", "")
                if name and (name.startswith("\\") or name.startswith("/") or ":" in name):
                    full = name
                else:
                    sep = "\\" if "\\" in directory else "/"
                    full = directory.rstrip("\\/") + sep + name
                yield {"filename": full, "size": int(f.get("size", 0))}
            for sub in d.get("directories", []) or []:
                yield from iter_files(sub)

        to_enqueue: List[Dict[str, Any]] = []
        for d in items:
            for f in iter_files(d):
                to_enqueue.append(f)
                if limit and len(to_enqueue) >= limit:
                    break
            if limit and len(to_enqueue) >= limit:
                break
        if not to_enqueue:
            return 0
        # API expects per-user batches; here it's same user
        ok = self.enqueue_downloads(username, to_enqueue)
        return len(to_enqueue) if ok else 0

    def list_downloads_all(self, include_removed: bool = False) -> List[Transfer]:
        self._ensure()
        return self._client.transfers.get_all_downloads(includeRemoved=include_removed)

    def list_uploads_all(self, include_removed: bool = False) -> List[Transfer]:
        self._ensure()
        return self._client.transfers.get_all_uploads(includeRemoved=include_removed)

    def cancel_download(self, username: str, file_id: str, remove: bool = False) -> bool:
        self._ensure()
        return self._client.transfers.cancel_download(username, file_id, remove=remove)

    def remove_completed_downloads(self) -> bool:
        self._ensure()
        return self._client.transfers.remove_completed_downloads()

    def cancel_upload(self, username: str, file_id: str, remove: bool = False) -> bool:
        self._ensure()
        return self._client.transfers.cancel_upload(username, file_id, remove=remove)

    def remove_completed_uploads(self) -> bool:
        self._ensure()
        return self._client.transfers.remove_completed_uploads()

    # Options / YAML (remote configuration must be enabled on slskd)
    def options_download_yaml(self) -> str:
        self._ensure()
        return self._client.options.download_yaml()

    def options_upload_yaml(self, yaml_text: str) -> bool:
        self._ensure()
        return self._client.options.upload_yaml(yaml_text)

    def options_validate_yaml(self, yaml_text: str) -> str:
        self._ensure()
        return self._client.options.validate_yaml(yaml_text)

    def shares_list(self):
        self._ensure()
        return self._client.shares.get_all()

    def shares_rescan(self) -> bool:
        self._ensure()
        return self._client.shares.start_scan()

    # Rooms
    def rooms_join(self, name: str) -> Room:
        self._ensure()
        return self._client.rooms.join(name)

    def rooms_leave(self, name: str) -> bool:
        self._ensure()
        return self._client.rooms.leave(name)

    def rooms_joined(self) -> List[str]:
        self._ensure()
        return self._client.rooms.get_all_joined()

    def rooms_messages(self, name: str) -> List[RoomMessage]:
        self._ensure()
        return self._client.rooms.get_messages(name)

    def rooms_send(self, name: str, message: str) -> bool:
        self._ensure()
        return self._client.rooms.send(name, message)

    def rooms_available(self) -> List[RoomInfo]:
        self._ensure()
        return self._client.rooms.get_all()

    # Users / Browse
    def user_browse(self, username: str) -> UserRootDir:
        self._ensure()
        return self._client.users.browse(username)

    def user_info(self, username: str):
        """Fetch user info (includes queueLength, uploadSlots, etc.)."""
        self._ensure()
        return self._client.users.info(username)

    # Private messages
    def pm_send(self, username: str, message: str) -> bool:
        self._ensure()
        return self._client.conversations.send(username, message)

    def conversations(self) -> List[Conversation]:
        self._ensure()
        return self._client.conversations.get_all()

    def _ensure(self):
        if not self._client:
            self.connect()
