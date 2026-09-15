from __future__ import annotations

import webbrowser
from collections.abc import Callable


ANTHROPIC_CONSOLE_URL = "https://console.anthropic.com/settings/keys"


def open_anthropic_console(opener: Callable[[str], object] = webbrowser.open) -> bool:
    result = opener(ANTHROPIC_CONSOLE_URL)
    return result is not False
