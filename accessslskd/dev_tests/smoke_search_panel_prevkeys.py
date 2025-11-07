"""
Headless smoke test to ensure SearchPanel repaints after starting a new search
even when the new results have the same keys as a prior search.
"""
from __future__ import annotations

import sys


def main() -> int:
    try:
        import wx  # type: ignore
    except Exception as e:
        print(f"SKIP: wxPython not available: {e}")
        return 0
    try:
        from accessslskd.ui.search_panel import SearchPanel  # type: ignore
    except Exception as e:
        print(f"FAIL: could not import SearchPanel: {e}")
        return 1

    class _DummyService:
        pass

    app = wx.App(False)
    frame = wx.Frame(None)
    try:
        panel = SearchPanel(frame, _DummyService(), lambda *_: None, auto_update=False)
        # Simulate a prior search producing this row/key
        row = {
            "username": "alice",
            "file": {"filename": "/music/song.mp3", "size": 123},
        }
        prior_key = panel._row_key(row)  # type: ignore[attr-defined]
        panel._prev_keys = [prior_key]   # type: ignore[attr-defined]

        # Start a "new search": UI clears list which must also reset _prev_keys
        panel._clear_list()  # type: ignore[attr-defined]

        # First fetch for the new search returns the same row.
        # Without the fix, repaint would be skipped and the list would stay empty.
        panel._after_fetch_once([row], state={}, timings=None)  # type: ignore[attr-defined]

        count = panel.lstFiles.GetItemCount()
        if count != 1:
            print(f"FAIL: expected 1 item after repaint, found {count}")
            return 1
        print("PASS: SearchPanel repaints correctly after new search.")
        return 0
    finally:
        try:
            frame.Destroy()
        except Exception:
            pass
        app.Destroy()


if __name__ == "__main__":
    raise SystemExit(main())

