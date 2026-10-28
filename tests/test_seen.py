"""Zapamatování naposledy vídaných záznamů nástěnky (potřebuje Home Assistant).

Bez balíčku ``homeassistant`` se přeskočí. Spuštění:
``pytest tests/test_seen.py -o asyncio_mode=auto`` v prostředí s pytest-homeassistant-custom-component.
"""

import pathlib
import sys
from datetime import date

import pytest

pytest.importorskip("homeassistant")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from custom_components.mojeodpadky.api import CollectedItem, diff_collected  # noqa: E402
from custom_components.mojeodpadky.coordinator import MojeOdpadkyCoordinator  # noqa: E402


def _coordinator(hass):
    return MojeOdpadkyCoordinator(hass, None, set(), 6, "entry1", None)


A = CollectedItem(date(2026, 9, 19), "Papír", "1A", "1")
B = CollectedItem(date(2026, 9, 12), "Plast", "2B", "1")
NOVY = CollectedItem(date(2026, 9, 21), "Sklo", "3C", "2")


async def test_nothing_remembered_on_fresh_install(hass):
    assert await _coordinator(hass)._async_seen() == []


async def test_remembered_records_survive_restart_and_new_ones_are_announced(hass):
    first = _coordinator(hass)
    await first._async_remember_seen([A, B])

    after_restart = _coordinator(hass)               # nová instance = nový start HA
    seen = await after_restart._async_seen()
    assert [i.key for i in seen] == [A.key, B.key]
    assert diff_collected(seen, [NOVY, A, B]) == [NOVY]
    assert diff_collected(seen, [A, B]) == []         # nic se neohlásí podruhé


async def test_empty_board_does_not_wipe_the_memory(hass):
    coordinator = _coordinator(hass)
    await coordinator._async_remember_seen([A, B])
    await coordinator._async_remember_seen([])        # výpadek nástěnky
    assert [i.key for i in await _coordinator(hass)._async_seen()] == [A.key, B.key]


async def test_same_records_are_not_written_again(hass, hass_storage):
    coordinator = _coordinator(hass)
    await coordinator._async_remember_seen([A, B])
    key = "mojeodpadky_entry1_collected"
    before = dict(hass_storage[key])
    await coordinator._async_remember_seen([A, B])
    assert hass_storage[key] == before


async def test_one_summary_event_per_refresh(hass):
    """Za obnovení jedna souhrnná událost; pytle sloučené, záznamy zvlášť."""
    from homeassistant.core import callback

    from types import SimpleNamespace

    coordinator = _coordinator(hass)
    coordinator.client = SimpleNamespace(slug="novalhota")
    zaznamy, souhrny = [], []
    hass.bus.async_listen("mojeodpadky_odevzdano", callback(lambda e: zaznamy.append(e.data)))
    hass.bus.async_listen("mojeodpadky_nova_odevzdani", callback(lambda e: souhrny.append(e.data)))
    plast = CollectedItem(date(2026, 10, 28), "Plast", "1BG102602", "3.4")
    papir = CollectedItem(date(2026, 10, 28), "Papír", "1BG102601", "3")
    coordinator._fire_new_collected([plast] * 4 + [papir] * 2)
    await hass.async_block_till_done()
    assert len(zaznamy) == 6
    assert len(souhrny) == 1
    assert souhrny[0]["pocet"] == 6
    assert [(r["komodita"], r["pocet"], r["ekobody_celkem"]) for r in souhrny[0]["zaznamy"]] == [
        ("Plast", 4, 13.6),
        ("Papír", 2, 6.0),
    ]
    coordinator._fire_new_collected([])
    await hass.async_block_till_done()
    assert len(souhrny) == 1
