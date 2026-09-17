"""Entrypoint for executing gram2email as a module (`python -m gram2email`)."""

import sys

from gram2email.cli import main

if __name__ == "__main__":
    sys.exit(main())
