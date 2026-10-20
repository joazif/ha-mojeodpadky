"""Opětovné přihlášení po změně hesla (potřebuje Home Assistant).

Bez balíčku ``homeassistant`` se přeskočí. Spuštění:
``pytest tests/ -o asyncio_mode=auto`` v prostředí s pytest-homeassistant-custom-component.
"""

import pathlib
import sys

import pytest

pytest.importorskip("homeassistant")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
FIXTURES = pathlib.Path(__file__).resolve().parent

from unittest.mock import patch  # noqa: E402
from homeassistant.config_entries import ConfigEntryState, SOURCE_REAUTH  # noqa: E402
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME  # noqa: E402
from homeassistant.data_entry_flow import FlowResultType  # noqa: E402
from homeassistant.exceptions import ConfigEntryAuthFailed  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402
from custom_components.mojeodpadky.api import InvalidAuth, MojeOdpadkyClient  # noqa: E402
from custom_components.mojeodpadky.const import DOMAIN, CONF_SLUG  # noqa: E402
from custom_components.mojeodpadky.coordinator import MojeOdpadkyCoordinator  # noqa: E402


@pytest.fixture(autouse=True)
def _custom_integrations(enable_custom_integrations):
    """Povolit načtení integrace z custom_components."""
    yield

# Smyšlený účet pro testy.
UCET = {"login": "uzivatel", "password": "stare", "slug": "novalhota"}


FETCH = "custom_components.mojeodpadky.api.MojeOdpadkyClient.async_fetch_page"


def _entry():
    return MockConfigEntry(
        domain=DOMAIN,
        title="Nová Lhota",
        unique_id="uzivatel@novalhota",
        data={CONF_USERNAME: "uzivatel", CONF_PASSWORD: "stare", CONF_SLUG: "novalhota"},
        options={"schedules": [], "scan_interval_hours": 6},
        version=1,
        minor_version=4,
    )


async def test_setup_with_bad_password_starts_reauth(hass):
    entry = _entry()
    entry.add_to_hass(hass)
    with patch(FETCH, side_effect=InvalidAuth("odmítnuto")):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == SOURCE_REAUTH
    assert flows[0]["step_id"] == "reauth_confirm"


async def test_reauth_flow(hass):
    entry = _entry()
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["description_placeholders"]["username"] == "uzivatel"

    with patch(FETCH, side_effect=InvalidAuth("odmítnuto")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "spatne"}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    from custom_components.mojeodpadky.api import MojeOdpadkyError
    with patch(FETCH, side_effect=MojeOdpadkyError("timeout")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "nove"}
        )
    assert result["errors"] == {"base": "cannot_connect"}

    with patch(FETCH, return_value="<html></html>"), patch(
        "custom_components.mojeodpadky.async_setup_entry", return_value=True
    ) as setup:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "nove"}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "nove"
    assert entry.data[CONF_USERNAME] == "uzivatel"
    assert entry.data[CONF_SLUG] == "novalhota"
    assert setup.called


async def test_runtime_auth_failure(hass):
    entry = _entry()
    entry.add_to_hass(hass)
    client = MojeOdpadkyClient(**UCET)
    coordinator = MojeOdpadkyCoordinator(hass, client, set(), 6, entry.entry_id, entry)
    with patch(FETCH, side_effect=InvalidAuth("odmítnuto")):
        with pytest.raises(ConfigEntryAuthFailed):
            await coordinator._async_update_data()
    await client.async_close()


async def test_runtime_refresh_starts_reauth(hass):
    """Plná cesta za běhu: plánovaná obnova -> odmítnuté heslo -> reauth flow."""
    entry = _entry()
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    client = MojeOdpadkyClient(**UCET)
    coordinator = MojeOdpadkyCoordinator(hass, client, set(), 6, entry.entry_id, entry)
    assert coordinator.config_entry is entry
    with patch(FETCH, side_effect=InvalidAuth("odmítnuto")):
        await coordinator.async_refresh()
        await hass.async_block_till_done()
    assert coordinator.last_update_success is False
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == [SOURCE_REAUTH]
    assert flows[0]["context"]["entry_id"] == entry.entry_id
    await client.async_close()


async def test_setup_bad_password_closes_session(hass):
    entry = _entry()
    entry.add_to_hass(hass)
    from homeassistant.helpers import aiohttp_client

    sessions = []
    puvodni = aiohttp_client.async_create_clientsession

    def create(hass, *args, **kwargs):
        sessions.append(puvodni(hass, *args, **kwargs))
        return sessions[-1]

    with patch(FETCH, side_effect=InvalidAuth("odmítnuto")), patch(
        "custom_components.mojeodpadky.async_create_clientsession", create
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    # Session služby odpojí HA sám i po nepovedeném načtení.
    assert len(sessions) == 1 and sessions[0].closed
