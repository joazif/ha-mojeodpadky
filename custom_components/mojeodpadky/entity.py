"""Společný základ entit."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MojeOdpadkyCoordinator


class MojeOdpadkyEntity(CoordinatorEntity[MojeOdpadkyCoordinator]):
    """Entita navázaná na jedno přihlášení."""

    _attr_has_entity_name = True

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
