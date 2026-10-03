"""Společný základ entit."""

from __future__ import annotations

from datetime import datetime

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MojeOdpadkyCoordinator


class MojeOdpadkyEntity(CoordinatorEntity[MojeOdpadkyCoordinator]):
    """Entita navázaná na jedno přihlášení."""

    _attr_has_entity_name = True
    # Stav závisí na dnešním datu (Zítra, Za 5 dní, zbývá 6 dní). Bez
    # přepočtu o půlnoci by se změnil až při dalším stažení dat - při
    # denním intervalu klidně o den později.
    _prepocitat_o_pulnoci = False

    def __init__(self, coordinator: MojeOdpadkyCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            # Jako služba: u jediného účtu obec, u dalšího v téže obci
            # obec a login. Starší instalace bez služby spadnou na obec.
            name=(
                coordinator.entry.title
                if coordinator.entry is not None
                else coordinator.client.town or coordinator.client.slug or "Svoz odpadu"
            ),
            manufacturer="mojeodpadky.cz",
            model=coordinator.client.slug or "",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=(
                f"https://www.mojeodpadky.cz/{coordinator.client.slug}/svozovy-kalendar"
                if coordinator.client.slug
                else "https://www.mojeodpadky.cz/"
            ),
        )

    async def async_added_to_hass(self) -> None:
        """Navíc naplánovat přepočet stavu po půlnoci."""
        await super().async_added_to_hass()
        if self._prepocitat_o_pulnoci:
            self.async_on_remove(
                async_track_time_change(
                    self.hass, self._po_pulnoci, hour=0, minute=0, second=5
                )
            )

    @callback
    def _po_pulnoci(self, _ted: datetime) -> None:
        """Nový den: přepočítat stav bez stahování dat."""
        self.async_write_ha_state()
