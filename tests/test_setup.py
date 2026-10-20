"""Celé načtení integrace nad uloženými stránkami a chování reloadu (potřebuje Home Assistant).

Bez balíčku ``homeassistant`` se přeskočí. Spuštění:
``pytest tests/ -o asyncio_mode=auto`` v prostředí s pytest-homeassistant-custom-component.
"""

import pathlib
import sys

import pytest

pytest.importorskip("homeassistant")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
FIXTURES = pathlib.Path(__file__).resolve().parent

from unittest.mock import AsyncMock, patch  # noqa: E402
from homeassistant.config_entries import ConfigEntryState  # noqa: E402
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME  # noqa: E402
from homeassistant.helpers import entity_registry as er  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402
from custom_components.mojeodpadky.const import DOMAIN, CONF_SLUG  # noqa: E402


@pytest.fixture(autouse=True)
def _custom_integrations(enable_custom_integrations):
    """Povolit načtení integrace z custom_components."""
    yield

# Smyšlený účet pro testy.
UCET = {"login": "uzivatel", "password": "stare", "slug": "novalhota"}


API = "custom_components.mojeodpadky.api.MojeOdpadkyClient"

def _f(n):
    return (FIXTURES / n).read_text(encoding="utf-8")


KAL, NAST, HOD, INV = _f("fixture_kalendar.html"), _f("fixture_nastenka.html"), _f("fixture_hodnoceni.html"), _f("fixture_inventura.html")


@pytest.fixture
def web():
    async def apply(self, wanted, unsubscribe=False, body=None):
        return body
    with patch(f"{API}.async_fetch_page", AsyncMock(return_value=KAL)), \
         patch(f"{API}.async_apply_selection", apply), \
         patch(f"{API}.async_fetch_town", AsyncMock(return_value="Nová Lhota")), \
         patch(f"{API}.async_fetch_collected", AsyncMock(return_value=NAST)), \
         patch(f"{API}.async_fetch_rating", AsyncMock(return_value=HOD)), \
         patch(f"{API}.async_fetch_inventory", AsyncMock(return_value=INV)), \
         patch(f"{API}.async_fetch_records_since", AsyncMock(return_value=[])):
        yield


def _entry():
    return MockConfigEntry(
        domain=DOMAIN, title="Nová Lhota", unique_id="uzivatel@novalhota",
        data={CONF_USERNAME: "uzivatel", CONF_PASSWORD: "heslo", CONF_SLUG: "novalhota"},
        options={"schedules": ["8001", "8002"], "scan_interval_hours": 6},
        version=1, minor_version=4,
    )


async def test_full_setup_and_unload(hass, web):
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    ents = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    domains = {e.domain for e in ents}
    assert {"sensor", "calendar", "button", "switch"} <= domains, domains
    unavailable = [e.entity_id for e in ents if (s := hass.states.get(e.entity_id)) and s.state == "unavailable"]
    print(len(ents), "entit; nedostupné:", unavailable)
    assert hass.states.get("calendar.nova_lhota") is not None
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_reload_only_on_real_change(hass, web):
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    with patch.object(hass.config_entries, "async_reload", AsyncMock()) as reload:
        # Stejný výběr jinak seřazený a změna dat (reauth) -> bez reloadu.
        hass.config_entries.async_update_entry(
            entry, options={"schedules": ["8002", "8001"], "scan_interval_hours": 6}
        )
        hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_PASSWORD: "nove"})
        await hass.async_block_till_done()
        assert reload.await_count == 0
        # Jiný interval -> reload.
        hass.config_entries.async_update_entry(
            entry, options={"schedules": ["8001", "8002"], "scan_interval_hours": 24}
        )
        await hass.async_block_till_done()
        assert reload.await_count == 1
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_options_flow_loaded(hass, web):
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"schedules": ["8001"], "scan_interval_hours": "24"}
    )
    await hass.async_block_till_done()
    assert entry.options == {"schedules": ["8001"], "scan_interval_hours": 24}
    assert entry.state is ConfigEntryState.LOADED
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_entity_ids_on_fresh_install(hass, web):
    """Počty mají ID s odevzdano_, svozy jen komoditu, řádek s rokem bez roku."""
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    ids = {e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)}
    for entity_id in (
        "calendar.nova_lhota",
        "sensor.nova_lhota_papir",
        "sensor.nova_lhota_odevzdano_papir",
        "sensor.nova_lhota_odevzdano_celkem",
        "sensor.nova_lhota_obdobi_odevzdani",
    ):
        assert entity_id in ids, sorted(ids)
    assert not [i for i in ids if i.endswith("_2")], sorted(ids)
    # Názvy z překladů (testy běží anglicky) a MESOH rok z nástěnky.
    assert hass.states.get("sensor.nova_lhota_odevzdano_celkem").name == "Nová Lhota Σ Total"
    assert hass.states.get("sensor.nova_lhota_obdobi_odevzdani").name.startswith("Nová Lhota 20")
    # E-mail z webu nepatří do atributů přepínačů.
    for state in hass.states.async_all("switch"):
        assert "email" not in state.attributes, state.attributes
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_user_agent_reaches_server(hass, aioclient_mock):
    """Session od HA má výchozí svůj User-Agent; klient musí poslat svůj."""
    from homeassistant.helpers.aiohttp_client import async_create_clientsession
    from custom_components.mojeodpadky.api import USER_AGENT, MojeOdpadkyClient

    url = "https://www.mojeodpadky.cz/novalhota"
    aioclient_mock.get(url, text="<title>Aktuality Nová Lhota | Moje odpadky</title>")
    client = MojeOdpadkyClient(**UCET, session=async_create_clientsession(hass))
    assert await client.async_fetch_town() == "Nová Lhota"
    hlavicky = aioclient_mock.mock_calls[0][3]
    assert hlavicky["User-Agent"] == USER_AGENT
