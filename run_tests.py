"""Compatibility entry point; selection lives only in scripts/run_tests.py."""
from scripts.run_tests import main

if __name__ == "__main__":
    raise SystemExit(main())
