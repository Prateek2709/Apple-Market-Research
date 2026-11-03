"""Entry point: `python run.py collect|list ...` (see market_signals/run.py)."""

import sys

from market_signals.run import main

if __name__ == "__main__":
    sys.exit(main())
