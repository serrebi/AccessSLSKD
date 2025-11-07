import os
import sys

# Allow running this file directly (path to __main__.py)
if __package__ is None and __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from accessslskd.app import main

if __name__ == "__main__":
    raise SystemExit(main())
