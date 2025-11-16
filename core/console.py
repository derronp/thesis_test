# core/console.py
from __future__ import annotations
import sys, io, os

def _safe_print_line(s: str):
    """
    Print a line robustly:
    - Prefer sys.stdout
    - Fallback to sys.__stdout__ if stdout is closed/redirected
    - Never raise; silently drop if both unavailable
    """
    # Try regular stdout
    try:
        print(s)
        return
    except Exception:
        pass

    # Try the original stdout
    try:
        if hasattr(sys, "__stdout__") and sys.__stdout__:
            sys.__stdout__.write(s + "\n")
            try:
                sys.__stdout__.flush()
            except Exception:
                pass
            return
    except Exception:
        pass
    # Last resort: do nothing (avoid crashing on logging)

def enable_utf8_stdout():
    """Best-effort: avoid UnicodeEncodeError on Windows consoles."""
    if os.name == "nt":
        # If stdout is missing/closed, try to restore from __stdout__
        if not getattr(sys, "stdout", None):
            try:
                sys.stdout = sys.__stdout__
            except Exception:
                return
        # If stdout lacks buffer or is closed, try to wrap
        try:
            if hasattr(sys.stdout, "buffer"):
                sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        except Exception:
            # Leave stdout as-is if wrapping fails
            pass

def emit_ok(msg: str):
    # Try emoji first; fallback to ASCII on any failure (encoding or closed stream)
    try:
        _safe_print_line("✅ " + msg)
    except Exception:
        _safe_print_line("[OK] " + msg)

def emit_fail(msg: str):
    try:
        _safe_print_line("❌ " + msg)
    except Exception:
        _safe_print_line("[FAIL] " + msg)

def emit_info(msg: str):
    try:
        _safe_print_line("ℹ️ " + msg)
    except Exception:
        _safe_print_line("[i] " + msg)

def emit_line(msg: str = ""):
    """Print a neutral line robustly (no icon)."""
    _safe_print_line(str(msg))

# Alias for convenience if you prefer this name:
safe_print = emit_line
