from __future__ import annotations

import base64
import ctypes
import os
from ctypes import wintypes


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes):
    buffer = ctypes.create_string_buffer(data)
    return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def protect(secret: str) -> str:
    if not secret:
        return ""
    if not hasattr(ctypes, "windll"):
        if os.environ.get("NEWSFLOW_TEST_MODE") == "1" and os.environ.get("NEWSFLOW_TEST_ROOT", "").strip():
            return "TEST:" + base64.b64encode(secret.encode("utf-8")).decode("ascii")
        raise RuntimeError("Windows DPAPI is required to protect NewsFlow secrets")
    source, keepalive = _blob(secret.encode("utf-8"))
    output = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(source), "Scriptor", None, None, None, 0, ctypes.byref(output)
    ):
        raise ctypes.WinError()
    try:
        raw = ctypes.string_at(output.pbData, output.cbData)
        return base64.b64encode(raw).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(output.pbData)


def unprotect(value: str) -> str:
    if not value:
        return ""
    if value.startswith("TEST:"):
        if os.environ.get("NEWSFLOW_TEST_MODE") == "1" and os.environ.get("NEWSFLOW_TEST_ROOT", "").strip():
            return base64.b64decode(value[5:]).decode("utf-8")
        raise RuntimeError("Test-only protected value cannot be opened outside NewsFlow test mode")
    if not hasattr(ctypes, "windll"):
        raise RuntimeError("Windows DPAPI is required to unprotect NewsFlow secrets")
    source, keepalive = _blob(base64.b64decode(value))
    output = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, 0, ctypes.byref(output)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output.pbData, output.cbData).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(output.pbData)
