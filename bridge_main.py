"""Console entry point for the bundled NewsFlow Python engine.

Electron starts this executable for each bridge request in portable builds,
so the desktop interface never relies on a separately installed Python.
"""

from scriptor.bridge import main


if __name__ == "__main__":
    main()
