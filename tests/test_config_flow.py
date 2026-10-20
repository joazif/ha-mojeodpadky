"""Průvodce přidáním, nastavení, chyby spojení a kalendář (potřebuje Home Assistant).

Bez balíčku ``homeassistant`` se přeskočí. Spuštění:
``pytest tests/ -o asyncio_mode=auto`` v prostředí s pytest-homeassistant-custom-component.
"""

import pathlib
import sys

import pytest

pytest.importorskip("homeassistant")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
FIXTURES = pathlib.Path(__file__).resolve().parent

from datetime import date, timedelta  # noqa: E402
from unittest.mock import AsyncMock, patch  # noqa: E402
import aiohttp  # noqa: E402
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME  # noqa: E402
from homeassistant.data_entry_flow import FlowResultType  # noqa: E402
from homeassistant.helpers.update_coordinator import UpdateFailed  # noqa: E402
from homeassistant.util import dt as dt_util  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402
from custom_components.mojeodpadky.api import MojeOdpadkyClient, MojeOdpadkyError  # noqa: E402
from custom_components.mojeodpadky.const import DOMAIN, CONF_SLUG  # noqa: E402
from custom_components.mojeodpadky.coordinator import MojeOdpadkyCoordinator  # noqa: E402


@pytest.fixture(autouse=True)
def _custom_integrations(enable_custom_integrations):
    """Povolit načtení integrace z custom_components."""
    yield

# Smyšlený účet pro testy.
UCET = {"login": "uzivatel", "password": "stare", "slug": "novalhota"}


API = "custom_components.mojeodpadky.api.MojeOdpadkyClient"
KALENDAR = (FIXTURES / "fixture_kalendar.html").read_text(encoding="utf-8")


def _entry(**kw):
    return MockConfigEntry(
        domain=DOMAIN, title="Nová Lhota", unique_id="uzivatel@novalhota",
        data={CONF_USERNAME: "uzivatel", CONF_PASSWORD: "heslo", CONF_SLUG: "novalhota"},
        options={"schedules": ["8001"], "scan_interval_hours": 6},
        version=1, minor_version=4, **kw,
    )


async def test_timeout_is_mojeodpadky_error():
    client = MojeOdpadkyClient(**UCET)
    with patch.object(client._session, "get", side_effect=TimeoutError()):
        with pytest.raises(MojeOdpadkyError):
            await client._get("https://www.mojeodpadky.cz/x")
    with patch.object(client._session, "post", side_effect=TimeoutError()):
        with pytest.raises(MojeOdpadkyError):
            await client.async_subscribe(1)
    await client.async_close()


async def test_user_flow_timeout_cannot_connect(hass):
    with patch(f"{API}._get", side_effect=MojeOdpadkyError("timeout")), patch.object(
        aiohttp.ClientSession, "post", side_effect=TimeoutError()
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_USERNAME: "uzivatel", CONF_PASSWORD: "heslo"}
        )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_unknown_error(hass):
    with patch(f"{API}.async_fetch_page", side_effect=RuntimeError("bum")):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_USERNAME: "uzivatel", CONF_PASSWORD: "heslo"}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


async def test_user_flow_already_configured_closes_session(hass):
    _entry().add_to_hass(hass)

    async def fetch(self):
        self._slug = "novalhota"
        return KALENDAR

    from homeassistant.helpers import aiohttp_client

    sessions = []
    puvodni = aiohttp_client.async_create_clientsession

    def create(hass, *args, **kwargs):
        sessions.append(puvodni(hass, *args, **kwargs))
        return sessions[-1]

    with patch(f"{API}.async_fetch_page", fetch), patch(
        f"{API}.async_fetch_town", AsyncMock(return_value="Nová Lhota")
    ), patch("custom_components.mojeodpadky.config_flow.async_create_clientsession", create):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_USERNAME: "Uzivatel", CONF_PASSWORD: "heslo"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    # Vlastní session průvodce, po ověření odpojená.
    assert len(sessions) == 1 and sessions[0].closed


async def test_user_flow_full(hass):
    async def fetch(self):
        self._slug = "novalhota"
        return KALENDAR

    with patch(f"{API}.async_fetch_page", fetch), patch(
        f"{API}.async_fetch_town", AsyncMock(return_value="Nová Lhota")
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_USERNAME: "uzivatel", CONF_PASSWORD: "heslo"}
        )
    assert result["step_id"] == "schedules"
    with patch("custom_components.mojeodpadky.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"schedules": ["8001"], "scan_interval_hours": "6"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Nová Lhota"
    assert result["data"][CONF_SLUG] == "novalhota"
    assert result["options"] == {"schedules": ["8001"], "scan_interval_hours": 6}


async def test_options_not_loaded_aborts(hass):
    entry = _entry()
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_loaded"


async def test_coordinator_unexpected_parse_error_is_update_failed(hass):
    entry = _entry()
    entry.add_to_hass(hass)
    client = MojeOdpadkyClient(**UCET)
    coordinator = MojeOdpadkyCoordinator(hass, client, {8001}, 6, entry.entry_id, entry)
    with patch(f"{API}.async_fetch_page", AsyncMock(return_value=KALENDAR)), patch(
        f"{API}.async_apply_selection", AsyncMock(side_effect=MojeOdpadkyError("x"))
    ):
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()
    with patch(f"{API}.async_fetch_page", AsyncMock(side_effect=MojeOdpadkyError("timeout"))):
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()
    await client.async_close()


async def test_calendar_range(hass):
    from custom_components.mojeodpadky.calendar import MojeOdpadkyCalendar
    from custom_components.mojeodpadky.coordinator import MojeOdpadkyData
    from custom_components.mojeodpadky.api import CollectionEvent

    entry = _entry()
    entry.add_to_hass(hass)
    client = MojeOdpadkyClient(**UCET)
    coordinator = MojeOdpadkyCoordinator(hass, client, set(), 6, entry.entry_id, entry)
    coordinator.data = MojeOdpadkyData(
        events=[CollectionEvent(date(2026, 10, d), "Papír", "H") for d in (5, 6, 7)],
        schedules=[],
    )
    cal = MojeOdpadkyCalendar(coordinator, entry.entry_id)
    start = dt_util.start_of_local_day(date(2026, 10, 6))
    events = await cal.async_get_events(hass, start, start + timedelta(days=1))
    assert [e.start for e in events] == [date(2026, 10, 6)]
    events = await cal.async_get_events(hass, start + timedelta(hours=12), start + timedelta(days=1, hours=1))
    assert [e.start for e in events] == [date(2026, 10, 6), date(2026, 10, 7)]
    await client.async_close()
