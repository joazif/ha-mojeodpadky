"""České popisky stavů senzorů.

Samostatný modul bez závislosti na Home Assistantu, aby šel testovat offline
stejně jako ``api.py``.
"""

from __future__ import annotations


def relative_future(days: int) -> str:
    """Popisek pro svoz, který teprve přijde: Dnes, Zítra, Za 3 dny, Za 15 dní."""
    if days <= 0:
        return "Dnes"
    if days == 1:
        return "Zítra"
    if days < 5:
        # 2-4: "Za 3 dny"
        return f"Za {days} dny"
    return f"Za {days} dní"


def relative_past(days: int) -> str:
    """Popisek pro odevzdání v minulosti: Dnes, Včera, Před 5 dny."""
    if days <= 0:
        return "Dnes"
    if days == 1:
        return "Včera"
    return f"Před {days} dny"
