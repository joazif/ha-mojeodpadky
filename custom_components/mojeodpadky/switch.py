"""Přepínače e-mailových upozornění po jednotlivých harmonogramech."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MojeOdpadkyConfigEntry
from .api import MojeOdpadkyError, Schedule, distinguish
from .coordinator import MojeOdpadkyCoordinator
from .entity import MojeOdpadkyEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MojeOdpadkyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Vytvořit přepínač pro každý sledovaný harmonogram."""
    coordinator = entry.runtime_data
    known: set[int] = set()

    @callback
    def _add_new() -> None:
        nove = [
            NotificationSwitch(coordinator, entry.entry_id, item.schedule_id)
            for item in (coordinator.data.schedules if coordinator.data else [])
            if item.subscribed and item.schedule_id not in known
        ]
        if nove:
            known.update(prepinac.schedule_id for prepinac in nove)
            async_add_entities(nove)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


class NotificationSwitch(MojeOdpadkyEntity, SwitchEntity):
    """E-mailová upozornění jednoho harmonogramu, jako tlačítko na webu."""

    _attr_icon = "mdi:email-alert-outline"

    def __init__(
        self,
        coordinator: MojeOdpadkyCoordinator,
        entry_id: str,
        schedule_id: int,
    ) -> None:
        super().__init__(coordinator, entry_id)
        self.schedule_id = schedule_id
        self._attr_unique_id = f"{entry_id}_notify_{schedule_id}"

    @property
    def _schedule(self) -> Schedule | None:
        for item in self.coordinator.data.schedules if self.coordinator.data else []:
            if item.schedule_id == self.schedule_id:
                return item
        return None

    @property
    def name(self) -> str:
        """Krátce, jen komodita.

        Když má víc sledovaných harmonogramů stejnou komoditu (obec má
        například bioodpad zvlášť pro dvě místní části), přidá se i ta část,
        jinak by byly přepínače k nerozeznání.
        """
        item = self._schedule
        if not item:
            return "Upozornění"

        # Porovnává se se všemi harmonogramy obce, ne jen se sledovanými.
        # Jinak by se název měnil podle toho, co je zrovna zaškrtnuté, a to
        # Home Assistant u už vzniklé entity stejně nepřepíše.
        stejne = [
            other
            for other in (
                self.coordinator.data.schedules if self.coordinator.data else []
            )
            if other.schedule_id != item.schedule_id
            and other.short_name == item.short_name
        ]
        rozliseni = distinguish(item, stejne)
        if rozliseni and rozliseni.lower() not in item.short_name.lower():
            return f"Upozornění: {item.short_name} {rozliseni}"
        return f"Upozornění: {item.short_name}"

    @property
    def available(self) -> bool:
        """Harmonogram, který se přestal sledovat, přepínat nejde."""
        item = self._schedule
        return super().available and item is not None and item.subscribed

    @property
    def is_on(self) -> bool:
        """Jestli web u tohoto harmonogramu posílá e-maily."""
        item = self._schedule
        return bool(item and item.notifications)

    @property
    def extra_state_attributes(self) -> dict:
        """Celý název harmonogramu, adresa a ID odběru."""
        item = self._schedule
        if not item:
            return {}
        return {
            "harmonogram": item.name,
            "email": self.coordinator.email,
            "id_odberu": item.subscribe_id,
        }

    async def async_turn_on(self, **kwargs) -> None:
        """Zapnout upozornění - odpovídá tlačítku na kartě harmonogramu."""
        item = self._schedule
        email = self.coordinator.email
        if not item or item.subscribe_id is None:
            raise HomeAssistantError("Harmonogram už není sledovaný")
        if not email:
            raise HomeAssistantError(
                "Na webu není vyplněná e-mailová adresa, doplňte ji tam nejdřív"
            )

        try:
            await self.coordinator.client.async_set_notification(
                item.subscribe_id, email, item.schedule_id
            )
        except MojeOdpadkyError as err:
            raise HomeAssistantError(str(err)) from err

        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        """Vypnout upozornění - odkaz „Vypnout upozornění" na kartě."""
        item = self._schedule
        if not item or item.subscribe_id is None:
            raise HomeAssistantError("Harmonogram už není sledovaný")

        try:
            await self.coordinator.client.async_unset_notification(item.subscribe_id)
        except MojeOdpadkyError as err:
            raise HomeAssistantError(str(err)) from err

        await self.coordinator.async_request_refresh()
