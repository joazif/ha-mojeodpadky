"""Přepínače e-mailových upozornění po jednotlivých komoditách."""

from __future__ import annotations

import logging
import re

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MojeOdpadkyConfigEntry
from .api import MojeOdpadkyError, Schedule, fingerprint, notification_name
from .const import DOMAIN
from .coordinator import MojeOdpadkyCoordinator
from .entity import MojeOdpadkyEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MojeOdpadkyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Vytvořit přepínač pro každou sledovanou komoditu."""
    coordinator = entry.runtime_data
    _prevest_stare_prepinace(hass, entry.entry_id, coordinator)
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        nove: dict[str, NotificationSwitch] = {}
        for item in coordinator.data.schedules if coordinator.data else []:
            otisk = fingerprint(item)
            if item.subscribed and otisk not in known and otisk not in nove:
                nove[otisk] = NotificationSwitch(coordinator, entry.entry_id, otisk)
        if nove:
            known.update(nove)
            async_add_entities(nove.values())

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


def _prevest_stare_prepinace(
    hass: HomeAssistant, entry_id: str, coordinator: MojeOdpadkyCoordinator
) -> None:
    """Přepínače ze starších instalací měly v unique_id ID harmonogramu.

    To se mění s každým novým ročníkem harmonogramu, takže by po přelomu
    roku vznikl nový přepínač a starý zůstal viset jako nedostupný. Tady
    se převedou na otisk komodity; entity_id i historie zůstanou.
    """
    registr = er.async_get(hass)
    vzor = re.compile(rf"^{re.escape(entry_id)}_notify_(\d+)$")
    podle_id = {
        item.schedule_id: item
        for item in (coordinator.data.schedules if coordinator.data else [])
    }
    for zaznam in er.async_entries_for_config_entry(registr, entry_id):
        shoda = vzor.match(zaznam.unique_id or "")
        if zaznam.domain != "switch" or not shoda:
            continue
        item = podle_id.get(int(shoda.group(1)))
        nove = f"{entry_id}_notify_{fingerprint(item)}" if item else None
        if nove and not registr.async_get_entity_id("switch", DOMAIN, nove):
            registr.async_update_entity(zaznam.entity_id, new_unique_id=nove)
            _LOGGER.debug("Přepínač %s převeden na %s", zaznam.entity_id, nove)
        else:
            # Harmonogram už na webu není, nebo jeho komoditu už zastupuje
            # jiný přepínač - starý by zůstal navždy nedostupný.
            registr.async_remove(zaznam.entity_id)
            _LOGGER.debug("Odstraněn starý přepínač %s", zaznam.entity_id)


class NotificationSwitch(MojeOdpadkyEntity, SwitchEntity):
    """E-mailová upozornění jedné komodity, jako tlačítko na webu.

    Nepatří konkrétnímu harmonogramu, ale komoditě v místní části. Nový
    ročník harmonogramu tak ovládá pořád stejný přepínač; když jsou chvíli
    sledované oba ročníky, přepíná se u obou.
    """

    _attr_icon = "mdi:email-alert-outline"

    def __init__(
        self,
        coordinator: MojeOdpadkyCoordinator,
        entry_id: str,
        otisk: str,
    ) -> None:
        super().__init__(coordinator, entry_id)
        self.otisk = otisk
        self._attr_unique_id = f"{entry_id}_notify_{otisk}"

    @property
    def _schedules(self) -> list[Schedule]:
        """Sledované harmonogramy této komodity, nejnovější první."""
        return sorted(
            (
                item
                for item in (
                    self.coordinator.data.schedules if self.coordinator.data else []
                )
                if item.subscribed and fingerprint(item) == self.otisk
            ),
            key=lambda item: item.schedule_id,
            reverse=True,
        )

    @property
    def name(self) -> str:
        """Krátce, jen komodita, případně s místní částí."""
        sledovane = self._schedules
        if not sledovane:
            return "Upozornění"
        return "Upozornění: " + notification_name(
            sledovane[0], self.coordinator.data.schedules
        )

    @property
    def available(self) -> bool:
        """Komoditu, která se přestala sledovat, přepínat nejde."""
        return super().available and bool(self._schedules)

    @property
    def is_on(self) -> bool:
        """Jestli web u této komodity posílá e-maily."""
        return any(item.notifications for item in self._schedules)

    @property
    def extra_state_attributes(self) -> dict:
        """Celé názvy harmonogramů, adresa a ID odběrů."""
        sledovane = self._schedules
        if not sledovane:
            return {}
        return {
            "harmonogram": ", ".join(item.name for item in sledovane),
            "email": self.coordinator.email,
            "id_odberu": ", ".join(
                str(item.subscribe_id) for item in sledovane if item.subscribe_id
            ),
        }

    async def async_turn_on(self, **kwargs) -> None:
        """Zapnout upozornění - odpovídá tlačítku na kartě harmonogramu."""
        email = self.coordinator.email
        cile = [
            item
            for item in self._schedules
            if item.subscribe_id is not None and not item.notifications
        ]
        if not self._schedules:
            raise HomeAssistantError("Harmonogram už není sledovaný")
        if not email:
            raise HomeAssistantError(
                "Na webu není vyplněná e-mailová adresa, doplňte ji tam nejdřív"
            )

        try:
            for item in cile:
                await self.coordinator.client.async_set_notification(
                    item.subscribe_id, email, item.schedule_id
                )
        except MojeOdpadkyError as err:
            raise HomeAssistantError(str(err)) from err

        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        """Vypnout upozornění - odkaz „Vypnout upozornění" na kartě."""
        cile = [
            item
            for item in self._schedules
            if item.subscribe_id is not None and item.notifications
        ]
        if not self._schedules:
            raise HomeAssistantError("Harmonogram už není sledovaný")

        try:
            for item in cile:
                await self.coordinator.client.async_unset_notification(
                    item.subscribe_id
                )
        except MojeOdpadkyError as err:
            raise HomeAssistantError(str(err)) from err

        await self.coordinator.async_request_refresh()
