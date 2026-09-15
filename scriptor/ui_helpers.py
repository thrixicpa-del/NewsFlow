from __future__ import annotations


_BY_KEYCODE = {67: "copy", 86: "paste", 88: "cut", 65: "select_all"}
_BY_KEYSYM = {"c": "copy", "v": "paste", "x": "cut", "a": "select_all"}


def clipboard_action(keysym: str, keycode: int) -> str | None:
    return _BY_KEYCODE.get(keycode) or _BY_KEYSYM.get((keysym or "").lower())
