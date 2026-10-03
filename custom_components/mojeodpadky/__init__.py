"""Integrace mojeodpadky.cz pro Home Assistant."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify

from .api import InvalidAuth, MojeOdpadkyClient, MojeOdpadkyError
from .const import (
    CONF_SCAN_INTERVAL,
    CONF_SCHEDULES,
    CONF_SLUG,
    DEFAULT_SCAN_INTERVAL_HOURS,
)
from .coordinator import MojeOdpadkyCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.CALENDAR,
    Platform.SENSOR,
    Platform.SWITCH,
]

if TYPE_CHECKING:
    MojeOdpadkyConfigEntry = ConfigEntry[MojeOdpadkyCoordinator]
else:
    MojeOdpadkyConfigEntry = ConfigEntry


async def async_setup_entry(
    hass: HomeAssistant, entry: MojeOdpadkyConfigEntry
) -> bool:
    """Nastavit integraci z config entry."""
    client = MojeOdpadkyClient(
        login=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        slug=entry.data.get(CONF_SLUG),
    )

    selected = {int(item) for item in entry.options.get(CONF_SCHEDULES, [])}
    interval = int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_HOURS))
    coordinator = MojeOdpadkyCoordinator(
        hass, client, selected, interval, entry.entry_id, entry
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        await client.async_close()
        raise
    except InvalidAuth as err:
        await client.async_close()
        raise ConfigEntryAuthFailed(str(err)) from err
    except MojeOdpadkyError as err:
        await client.async_close()
        raise ConfigEntryNotReady(str(err)) from err

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_migrate_entry(
    hass: HomeAssistant, entry: MojeOdpadkyConfigEntry
) -> bool:
    """Jednorázové úpravy starších instalací.

    1.1 -> 1.2: entity "EKO body: <komodita>" vznikaly viditelné, teď mají
    být skryté. Nastavení skrytosti v kódu platí jen pro nově vznikající
    entity a smazat entitu, kterou integrace pořád poskytuje, HA nedovolí -
    proto se už existující skryjí tady. Proběhne to jednou; když si je pak
    uživatel zase zobrazí, zůstanou zobrazené.
    """
    if entry.version == 1 and entry.minor_version < 2:
        registr = er.async_get(hass)
        skryto = 0
        for zaznam in er.async_entries_for_config_entry(registr, entry.entry_id):
            if "_points_" in (zaznam.unique_id or "") and zaznam.hidden_by is None:
                registr.async_update_entity(
                    zaznam.entity_id, hidden_by=er.RegistryEntryHider.INTEGRATION
                )
                skryto += 1
        hass.config_entries.async_update_entry(entry, minor_version=2)
        _LOGGER.info("Migrace na 1.2: skryto %s entit EKO body", skryto)

    if entry.version == 1 and entry.minor_version < 3:
        # 1.2 -> 1.3: EKO body už nejsou samostatné entity, ale atribut
        # počtů odevzdání. Skryté entity HA na stránce zařízení stejně
        # ukazoval, tak se z registru uklidí úplně.
        registr = er.async_get(hass)
        smazano = 0
        for zaznam in er.async_entries_for_config_entry(registr, entry.entry_id):
            if "_points_" in (zaznam.unique_id or ""):
                registr.async_remove(zaznam.entity_id)
                smazano += 1
        hass.config_entries.async_update_entry(entry, minor_version=3)
        _LOGGER.info("Migrace na 1.3: odstraněno %s entit EKO body", smazano)

    if entry.version == 1 and entry.minor_version < 4:
        # 1.3 -> 1.4: počty měly v ID rok (sensor.<obec>_26_papir), který
        # zastará hned první říjen. Nové ID je bez roku; HA s ním přenese
        # i historii a dlouhodobé statistiky.
        registr = er.async_get(hass)
        zarizeni = slugify(entry.title)
        predpona = f"{entry.entry_id}_count_"
        prejmenovano = 0
        for zaznam in er.async_entries_for_config_entry(registr, entry.entry_id):
            unique_id = zaznam.unique_id or ""
            if not unique_id.startswith(predpona):
                continue
            konec = unique_id[len(predpona):]
            nove_id = (
                f"sensor.{zarizeni}_odevzdano_celkem"
                if konec == "total"
                else f"sensor.{zarizeni}_odevzdano_{konec}"
            )
            if zaznam.entity_id == nove_id or registr.async_get(nove_id):
                continue
            registr.async_update_entity(zaznam.entity_id, new_entity_id=nove_id)
            prejmenovano += 1
        hass.config_entries.async_update_entry(entry, minor_version=4)
        _LOGGER.info("Migrace na 1.4: přejmenováno %s entit počtů", prejmenovano)

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: MojeOdpadkyConfigEntry
) -> bool:
    """Odpojit integraci."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.client.async_close()
    return unloaded


async def async_reload_entry(
    hass: HomeAssistant, entry: MojeOdpadkyConfigEntry
) -> None:
    """Po změně nastavení načíst znovu."""
    await hass.config_entries.async_reload(entry.entry_id)
