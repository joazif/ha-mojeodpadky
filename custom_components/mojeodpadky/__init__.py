"""Integrace mojeodpadky.cz pro Home Assistant."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

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
