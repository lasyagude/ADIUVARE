from __future__ import annotations

import ctypes
import html
import platform
import re
import unicodedata
import urllib.parse
from pathlib import Path

_decode_u = re.compile(r"\\u([0-9a-fA-F]{4})")
_sql_cmnt = re.compile(r"/\*.*?\*/", re.DOTALL)
_line_cmnt = re.compile(r"(--|#).*")
_noise = re.compile(r"[\r\n\x00\t]")
_lib = None
_bound = False


def _lib_name() -> str:
    if platform.system() == "Windows":
        return "libinjection.dll"
    if platform.system() == "Darwin":
        return "libinjection.dylib"
    return "libinjection.so"


def _lib_path() -> Path:
    return Path(__file__).with_name(_lib_name())


def _bind(lib) -> None:
    global _bound
    if _bound:
        return

    lib.libinjection_sqli.argtypes = [
        ctypes.c_char_p,
        ctypes.c_size_t,
        ctypes.c_char_p,
    ]
    lib.libinjection_sqli.restype = ctypes.c_int
    lib.libinjection_xss.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
    lib.libinjection_xss.restype = ctypes.c_int
    _bound = True


def _load_lib():
    global _lib
    if _lib is not None:
        return _lib

    lib_path = _lib_path()
    if not lib_path.exists():
        return None

    try:
        lib = ctypes.CDLL(str(lib_path))
    except OSError:
        return None

    _bind(lib)
    _lib = lib
    return _lib


def normalize(text: str | None, max_passes: int = 3) -> str:
    if not text:
        return ""

    text = _sql_cmnt.sub(" ", text)

    for _ in range(max_passes):
        prev = text
        text = _noise.sub(" ", text)
        text = urllib.parse.unquote_plus(text)
        text = html.unescape(text)
        text = _decode_u.sub(lambda m: chr(int(m.group(1), 16)), text)
        text = unicodedata.normalize("NFKC", text)
        if text == prev:
            break

    return _line_cmnt.sub("", text).strip()


def _fallback_sqli(text: str) -> dict:
    low = text.lower()
    hits = (
        "' or 1=1",
        "\" or 1=1",
        "union select",
        "sleep(",
        "benchmark(",
        "information_schema",
    )
    for needle in hits:
        if needle in low:
            return {"hit": True, "conf": 0.80, "fp": "fallback"}
    return {"hit": False, "conf": 0.0, "fp": ""}


def _fallback_xss(text: str) -> dict:
    low = text.lower()
    if "<script" in low or "javascript:" in low or "onerror=" in low:
        return {"hit": True, "conf": 0.80}
    return {"hit": False, "conf": 0.0}


def detect_sqli(text: str | None) -> dict:
    cleaned = normalize(text)
    lib = _load_lib()
    if lib is None:
        return _fallback_sqli(cleaned)

    raw = cleaned.encode("utf-8", errors="replace")
    fp = ctypes.create_string_buffer(32)
    try:
        hit = lib.libinjection_sqli(raw, len(raw), fp)
    except Exception:
        return _fallback_sqli(cleaned)

    if hit == 1:
        mark = fp.value.decode("ascii", errors="ignore").strip("\x00")
        return {"hit": True, "conf": 1.0, "fp": mark}

    return {"hit": False, "conf": 0.0, "fp": ""}


def detect_xss(text: str | None) -> dict:
    cleaned = normalize(text)
    lib = _load_lib()
    if lib is None:
        return _fallback_xss(cleaned)

    raw = cleaned.encode("utf-8", errors="replace")
    try:
        hit = lib.libinjection_xss(raw, len(raw))
    except Exception:
        return _fallback_xss(cleaned)

    return {"hit": hit == 1, "conf": 1.0 if hit == 1 else 0.0}
