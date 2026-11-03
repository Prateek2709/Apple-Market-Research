"""`python -m market_signals.collectors <source> ...` runs the named collectors (same as run.py collect)."""

import sys

from market_signals.run import main

if __name__ == "__main__":
    args = sys.argv[1:]
    sys.exit(main(["collect", "--sources", ",".join(args)] if args and not args[0].startswith("-") else ["collect", *args]))
