"""Kalendářová entita se svozy odpadu."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import (
    CalendarEntity,
    CalendarEvent,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import MojeOdpadkyConfigEntry
from .entity import MojeOdpadkyEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MojeOdpadkyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Vytvořit kalendář."""
    async_add_entities([MojeOdpadkyCalendar(entry.runtime_data, entry.entry_id)])


class MojeOdpadkyCalendar(MojeOdpadkyEntity, CalendarEntity):
    """Všechny svozy jako celodenní události."""

    # Hlavní entita zařízení: název None znamená, že se jmenuje jako
    # zařízení (obec). Home Assistant ji díky tomu vykreslí nahoře
    # a oddělí čarou od ostatních - přesně o tu čáru tu jde.
    _attr_name = None
    _attr_icon = "mdi:calendar-month"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_calendar"

    @property
    def event(self) -> CalendarEvent | None:
        """Nejbližší svoz."""
        event = self.coordinator.next_event()
        return _to_calendar_event(event) if event else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Svozy ve zvoleném rozsahu."""
        if not self.coordinator.data:
            return []

        start = dt_util.as_local(start_date).date()
        end = dt_util.as_local(end_date).date()

        return [
            _to_calendar_event(event)
            for event in self.coordinator.data.events
            if start <= event.day <= end
        ]


def _to_calendar_event(event) -> CalendarEvent:
    return CalendarEvent(
        summary=event.waste_type,
        description=event.schedule_name,
        start=event.day,
        end=event.day + timedelta(days=1),
        # Do uid patří i harmonogram: dvě obce v jednom dni se stejnou
        # komoditou by jinak vyrobily dvě události se shodným uid.
        uid=f"{event.day.isoformat()}-{event.waste_type}-{event.schedule_name}",
    )
