"""Tlačítko pro ruční aktualizaci dat."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MojeOdpadkyConfigEntry
from .coordinator import MojeOdpadkyCoordinator
from .entity import MojeOdpadkyEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MojeOdpadkyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Vytvořit tlačítko aktualizace."""
    async_add_entities([RefreshButton(entry.runtime_data, entry.entry_id)])


class RefreshButton(MojeOdpadkyEntity, ButtonEntity):
    """Stáhne data hned, bez čekání na další interval."""

    _attr_translation_key = "refresh"
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: MojeOdpadkyCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_refresh"

    async def async_press(self) -> None:
        """Stáhnout data znovu."""
        await self.coordinator.async_request_refresh()
