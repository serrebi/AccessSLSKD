import os
import sys

# Ensure local package import works when double-clicked
sys.path.insert(0, os.path.dirname(__file__))

from accessslskd.app import main

if __name__ == "__main__":
    raise SystemExit(main())

