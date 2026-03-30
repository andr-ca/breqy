"""System clipboard fallback for environments where OSC 52 is unreliable.

Tries platform-appropriate clipboard tools in order:

1. ``xclip``  (X11 Linux)
2. ``xsel``   (X11 Linux alternative)
3. ``wl-copy`` (Wayland Linux)
4. ``pbcopy`` (macOS)

Failures are logged but never raised — clipboard is best-effort.
"""

from __future__ import annotations

import subprocess

import structlog

logger = structlog.get_logger(__name__)

_CLIPBOARD_TOOLS: list[list[str]] = [
    ["xclip", "-selection", "clipboard"],
    ["xsel", "--clipboard", "--input"],
    ["wl-copy"],
    ["pbcopy"],
]


def copy_to_system_clipboard(text: str) -> None:
    """Copy *text* to the system clipboard via a subprocess tool.

    Tries each tool in ``_CLIPBOARD_TOOLS`` until one succeeds.
    All errors are caught and logged; this function never raises.
    """
    if not text:
        return

    for cmd in _CLIPBOARD_TOOLS:
        try:
            subprocess.run(
                cmd,
                input=text,
                text=True,
                check=True,
                timeout=2,
                capture_output=True,
            )
            logger.debug("Copied to system clipboard", tool=cmd[0], length=len(text))
            return
        except FileNotFoundError:
            continue
        except (subprocess.SubprocessError, OSError) as exc:
            logger.debug("Clipboard tool failed", tool=cmd[0], error=str(exc))
            continue

    logger.debug("No system clipboard tool available")
