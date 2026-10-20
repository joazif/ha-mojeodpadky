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


async def test_switches_named_by_waste_type(hass, web):
    """Přepínač na komoditu ze svozů, bez místní části a roku."""
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    jmena = {s.entity_id: s.name for s in hass.states.async_all("switch")}
    assert jmena == {
        "switch.nova_lhota_upozorneni_bio": "Nová Lhota Upozornění: Bio",
        "switch.nova_lhota_upozorneni_papir": "Nová Lhota Upozornění: Papír",
        "switch.nova_lhota_upozorneni_plast": "Nová Lhota Upozornění: Plast",
        "switch.nova_lhota_upozorneni_smesny_odpad": "Nová Lhota Upozornění: Směsný odpad",
    }, jmena
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_old_switches_converted(hass, web):
    """Přepínače ze starších verzí se převedou, duplicity a roky uklidí."""
    entry = _entry()
    entry.add_to_hass(hass)
    registr = er.async_get(hass)
    p = f"{entry.entry_id}_notify_"

    def stary(klic, objekt):
        return registr.async_get_or_create(
            "switch", DOMAIN, p + klic, suggested_object_id=objekt, config_entry=entry
        ).entity_id

    papir = stary("papír|nová", "nova_lhota_upozorneni_papir_nova")
    bio_2027 = stary("bioodpad|nová", "nova_lhota_upozorneni_harmonogram_bio_nova_2027")
    plast = stary("8004", "nova_lhota_upozorneni_plast_nova")
    smesny = stary("směsný odpad|", "nova_lhota_upozorneni_smesny_odpad")
    smesny_dvakrat = stary("8001", "nova_lhota_upozorneni_harmonogram_smesny_odpad_20207")
    zmizely = stary("sklo|", "nova_lhota_upozorneni_sklo")

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    def uid(entity_id):
        zaznam = registr.async_get(entity_id)
        return zaznam.unique_id[len(p):] if zaznam else None

    # Bez roku v ID: ID zůstane, klíč se převede.
    assert uid(papir) == "papír"
    assert uid(plast) == "plast"
    assert uid(smesny) == "směsný odpad"
    # S rokem v ID: jednou přejmenováno na čisté.
    assert uid(bio_2027) is None
    assert uid("switch.nova_lhota_upozorneni_bio") == "bio"
    # Druhý přepínač téže komodity a harmonogram, který už na webu není.
    assert uid(smesny_dvakrat) is None
    assert uid(zmizely) is None
    zbyle = sorted(
        z.unique_id[len(p):]
        for z in er.async_entries_for_config_entry(registr, entry.entry_id)
        if z.domain == "switch"
    )
    assert zbyle == ["bio", "papír", "plast", "směsný odpad"], zbyle
    assert hass.states.get(papir).name == "Nová Lhota Upozornění: Papír"
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_switch_removed_when_schedule_gone(hass, web):
    """Komodita bez sledovaného harmonogramu nezůstane viset jako nedostupná."""
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    for item in coordinator.data.schedules:
        if item.schedule_id == 8004:
            item.subscribed = False
    coordinator.async_update_listeners()
    await hass.async_block_till_done()
    assert hass.states.get("switch.nova_lhota_upozorneni_plast") is None
    assert er.async_get(hass).async_get("switch.nova_lhota_upozorneni_plast") is None
    assert hass.states.get("switch.nova_lhota_upozorneni_papir") is not None
    # Prázdná stránka (chyba čtení) nemaže nic.
    schedules = coordinator.data.schedules
    coordinator.data.schedules = []
    coordinator.async_update_listeners()
    await hass.async_block_till_done()
    assert hass.states.get("switch.nova_lhota_upozorneni_papir") is not None
    coordinator.data.schedules = schedules
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_waste_type_sensor_without_collections_disappears(hass, web):
    """Komodita bez dalšího svozu nemá viset jako "Neznámý"; vrátí se sama."""
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registr = er.async_get(hass)
    coordinator = entry.runtime_data
    assert hass.states.get("sensor.nova_lhota_papir") is not None

    vsechny = coordinator.data.events
    coordinator.data.events = [e for e in vsechny if e.waste_type != "Papír"]
    coordinator.async_update_listeners()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.nova_lhota_papir") is None
    assert registr.async_get("sensor.nova_lhota_papir") is None
    # Ostatní komodity, pevné senzory i počty zůstanou.
    for entity_id in (
        "sensor.nova_lhota_plast",
        "sensor.nova_lhota_bio",
        "sensor.nova_lhota_odevzdano_papir",
        "sensor.nova_lhota_odevzdano_celkem",
        "sensor.nova_lhota_obdobi_odevzdani",
    ):
        assert registr.async_get(entity_id) is not None, entity_id

    # Prázdný kalendář (chyba čtení) nemaže nic.
    coordinator.data.events = []
    coordinator.async_update_listeners()
    await hass.async_block_till_done()
    assert registr.async_get("sensor.nova_lhota_plast") is not None

    # Svozy papíru se vrátí -> senzor vznikne znovu se stejným ID.
    coordinator.data.events = vsechny
    coordinator.async_update_listeners()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.nova_lhota_papir") is not None
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_options_show_what_is_subscribed_on_web(hass, web):
    """Formulář ukáže skutečný stav webu, ne výběr z doby instalace.

    Web sám přihlásil další harmonogramy (nový ročník); kdyby tu nebyly
    zaškrtnuté, uložení formuláře by je na webu odhlásilo.
    """
    entry = _entry()
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry, options={"schedules": ["8001"], "scan_interval_hours": 6}
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    vychozi = next(
        klic.default() for klic in result["data_schema"].schema if klic == "schedules"
    )
    assert sorted(vychozi) == ["8001", "8004", "8005", "8006"], vychozi
    hass.config_entries.options.async_abort(result["flow_id"])
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_vanished_schedule_dropped_from_selection(hass, web, caplog):
    """Harmonogram, který z webu zmizel bez nástupce, se tiše vyřadí."""
    entry = _entry()
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry, options={"schedules": ["8001", "1234"], "scan_interval_hours": 6}
    )
    with patch.object(hass.config_entries, "async_reload", AsyncMock()) as reload:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.options["schedules"] == ["8001"]
        assert entry.runtime_data.selected == {8001}
        # Druhá obnova už nic nehlásí.
        caplog.clear()
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert "nástupce se nenašel" not in caplog.text
        assert reload.await_count == 0
    assert not [r for r in caplog.records if r.levelname == "WARNING" and "mojeodpadky" in r.name]
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
