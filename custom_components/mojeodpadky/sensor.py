"""Senzory příštích svozů a odevzdaného odpadu."""

from __future__ import annotations

import re
import unicodedata

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MojeOdpadkyConfigEntry
from .const import (
    ATTR_CONTAINER,
    ATTR_DATE,
    ATTR_DAYS_TO,
    ATTR_POINTS,
    ATTR_RECORDS,
    ATTR_SCHEDULE,
    ATTR_TYPES,
    ATTR_WASTE_TYPE,
)
from .coordinator import MojeOdpadkyCoordinator, dt_today
from .entity import MojeOdpadkyEntity
from .texts import relative_future, relative_past

ICONS = {
    "Směsný odpad": "mdi:trash-can",
    "Směsný": "mdi:trash-can",
    "Plast": "mdi:recycle",
    "Papír": "mdi:newspaper-variant-multiple",
    "Bio": "mdi:leaf",
    "Bioodpad": "mdi:leaf",
    "Sklo": "mdi:bottle-wine",
    "Kov": "mdi:silverware-fork-knife",
    "Kovy": "mdi:silverware-fork-knife",
    "Elektro": "mdi:television-classic",
    "Dřevo": "mdi:pine-tree",
    "Pneumatiky": "mdi:tire",
    "Suť": "mdi:wall",
    "Textil": "mdi:tshirt-crew",
    "Jedlý olej a tuk": "mdi:oil",
    # Nebezpečný odpad, na nástěnce zkratkou.
    "NO": "mdi:biohazard",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MojeOdpadkyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Vytvořit senzory - souhrnný, jeden na komoditu a jeden z nástěnky."""
    coordinator = entry.runtime_data

    entities: list[SensorEntity] = [
        NextCollectionSensor(coordinator, entry.entry_id),
        LastCollectedSensor(coordinator, entry.entry_id),
        LastUpdateSensor(coordinator, entry.entry_id),
        FeeSensor(coordinator, entry.entry_id),
        FeePartSensor(coordinator, entry.entry_id, "rate"),
        FeePartSensor(coordinator, entry.entry_id, "discount"),
        FeePartSensor(coordinator, entry.entry_id, "discount_percent"),
        ScorePointsSensor(coordinator, entry.entry_id),
        ScoreUsageSensor(coordinator, entry.entry_id),
        VolumeSensor(coordinator, entry.entry_id),
        PeopleSensor(coordinator, entry.entry_id),
    ]
    known: set[str] = set()

    @callback
    def _add_new_types() -> None:
        new = [
            WasteTypeSensor(coordinator, entry.entry_id, waste_type)
            for waste_type in coordinator.waste_types
            if waste_type not in known
        ]
        if new:
            known.update(sensor.waste_type for sensor in new)
            async_add_entities(new)

    _add_new_types()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_types))

    async_add_entities(entities)


class NextCollectionSensor(MojeOdpadkyEntity, SensorEntity):
    """Nejbližší svoz bez ohledu na komoditu.

    Stav je český popisek (Dnes, Zítra, Za 5 dní), protože takhle to má být
    vidět v seznamu entit. Datum i počet dní jsou v atributech, automatizace
    se mají vázat na ně, ne na text.
    """

    _attr_translation_key = "next_collection"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: MojeOdpadkyCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_next_collection"

    @property
    def native_value(self) -> str | None:
        """Za jak dlouho je nejbližší svoz."""
        event = self.coordinator.next_event()
        return relative_future((event.day - dt_today()).days) if event else None

    @property
    def extra_state_attributes(self) -> dict:
        """Datum, počet dní a komodity svážené v ten den."""
        upcoming = self.coordinator.upcoming()
        if not upcoming:
            return {}
        day = upcoming[0].day
        same_day = [event for event in upcoming if event.day == day]
        return {
            ATTR_DATE: day.isoformat(),
            ATTR_DAYS_TO: (day - dt_today()).days,
            ATTR_TYPES: sorted({event.waste_type for event in same_day}),
        }


class WasteTypeSensor(MojeOdpadkyEntity, SensorEntity):
    """Nejbližší svoz jedné komodity."""

    def __init__(
        self, coordinator: MojeOdpadkyCoordinator, entry_id: str, waste_type: str
    ) -> None:
        super().__init__(coordinator, entry_id)
        self.waste_type = waste_type
        self._attr_name = waste_type
        self._attr_unique_id = f"{entry_id}_{_slug(waste_type)}"
        self._attr_icon = ICONS.get(waste_type, "mdi:trash-can-outline")

    @property
    def native_value(self) -> str | None:
        """Za jak dlouho se komodita sveze."""
        event = self.coordinator.next_event(self.waste_type)
        return relative_future((event.day - dt_today()).days) if event else None

    @property
    def extra_state_attributes(self) -> dict:
        """Datum svozu, počet dní a název harmonogramu."""
        event = self.coordinator.next_event(self.waste_type)
        if not event:
            return {}
        return {
            ATTR_DATE: event.day.isoformat(),
            ATTR_DAYS_TO: (event.day - dt_today()).days,
            ATTR_SCHEDULE: event.schedule_name,
        }


class LastCollectedSensor(MojeOdpadkyEntity, SensorEntity):
    """Poslední odevzdaný odpad a seznam posledních 15 záznamů z nástěnky."""

    _attr_translation_key = "last_collected"
    _attr_icon = "mdi:package-variant-closed-check"

    def __init__(self, coordinator: MojeOdpadkyCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_last_collected"

    @property
    def native_value(self) -> str | None:
        """Jak dávno bylo poslední odevzdání: Dnes, Včera, Před 5 dny."""
        collected = self.coordinator.collected
        if not collected:
            return None
        return relative_past((dt_today() - collected[0].day).days)

    @property
    def extra_state_attributes(self) -> dict:
        """Poslední záznam rozepsaný a seznam posledních 15 odevzdání."""
        collected = self.coordinator.collected
        if not collected:
            return {}
        last = collected[0]
        return {
            ATTR_DATE: last.day.isoformat(),
            ATTR_WASTE_TYPE: last.waste_type,
            ATTR_CONTAINER: last.container,
            ATTR_RECORDS: [
                {
                    ATTR_DATE: item.day.isoformat(),
                    ATTR_WASTE_TYPE: item.waste_type,
                    ATTR_CONTAINER: item.container,
                    ATTR_POINTS: item.points,
                }
                for item in collected
            ],
        }


class FeeSensor(MojeOdpadkyEntity, SensorEntity):
    """Předpokládaný poplatek za odpady po odečtení úlevy MESOH."""

    _attr_translation_key = "fee"
    _attr_icon = "mdi:cash"
    _attr_native_unit_of_measurement = "Kč"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: MojeOdpadkyCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_fee"

    @property
    def native_value(self) -> int | None:
        """Kolik se bude platit na osobu po úlevě."""
        fee = self.coordinator.fee
        return fee.total if fee else None

    @property
    def extra_state_attributes(self) -> dict:
        """Rok, plná sazba a úleva."""
        fee = self.coordinator.fee
        if not fee:
            return {}
        return {
            "rok": fee.year,
            "sazba": fee.rate,
            "uleva": fee.discount,
            "uleva_procent": fee.discount_percent,
        }


class FeePartSensor(MojeOdpadkyEntity, SensorEntity):
    """Jednotlivá čísla poplatku zvlášť, ať je Home Assistant archivuje.

    Atributy se do dlouhodobých statistik neukládají, takže sazba a úleva
    musí být samostatné entity, jinak se z nich nikdy nedá udělat graf.
    """

    _attr_state_class = SensorStateClass.MEASUREMENT

    POPIS = {
        "rate": ("fee_rate", "mdi:cash-multiple", "Kč"),
        "discount": ("fee_discount", "mdi:sale", "Kč"),
        "discount_percent": ("fee_discount_percent", "mdi:percent-outline", "%"),
    }

    def __init__(
        self, coordinator: MojeOdpadkyCoordinator, entry_id: str, cast: str
    ) -> None:
        super().__init__(coordinator, entry_id)
        klic, ikona, jednotka = self.POPIS[cast]
        self._cast = cast
        self._attr_translation_key = klic
        self._attr_icon = ikona
        self._attr_native_unit_of_measurement = jednotka
        self._attr_unique_id = f"{entry_id}_{klic}"
        if cast == "discount_percent":
            self._attr_suggested_display_precision = 1

    @property
    def native_value(self) -> float | int | None:
        """Sazba, úleva v korunách, nebo úleva v procentech."""
        fee = self.coordinator.fee
        return getattr(fee, self._cast) if fee else None

    @property
    def extra_state_attributes(self) -> dict:
        """Za který rok to platí."""
        fee = self.coordinator.fee
        return {"rok": fee.year} if fee else {}


class ScorePointsSensor(MojeOdpadkyEntity, SensorEntity):
    """EKO body na osobu z motivačního systému MESOH."""

    _attr_translation_key = "score_points"
    _attr_icon = "mdi:star-circle-outline"
    _attr_native_unit_of_measurement = "bodů"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: MojeOdpadkyCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_score_points"

    @property
    def native_value(self) -> float | None:
        """Získané body na osobu."""
        score = self.coordinator.score
        return score.points if score else None

    @property
    def extra_state_attributes(self) -> dict:
        """Kolik bodů jde získat celkem a kolik z toho je využito."""
        score = self.coordinator.score
        if not score:
            return {}
        return {"maximum": score.max_points, "vyuziti_procent": score.percent}


class ScoreUsageSensor(MojeOdpadkyEntity, SensorEntity):
    """Na kolik procent je využitý potenciál motivačního systému."""

    _attr_translation_key = "score_usage"
    _attr_icon = "mdi:gauge"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: MojeOdpadkyCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_score_usage"

    @property
    def native_value(self) -> float | None:
        """Využití potenciálu v procentech."""
        score = self.coordinator.score
        return score.percent if score else None

    @property
    def extra_state_attributes(self) -> dict:
        """Body, ze kterých se procento počítá."""
        score = self.coordinator.score
        if not score:
            return {}
        return {"body": score.points, "maximum": score.max_points}


class VolumeSensor(MojeOdpadkyEntity, SensorEntity):
    """Obsloužený objem odpadu na osobu za probíhající MESOH rok."""

    _attr_translation_key = "volume_person"
    _attr_icon = "mdi:delete-variant"
    _attr_native_unit_of_measurement = "l"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: MojeOdpadkyCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_volume_person"

    @property
    def native_value(self) -> float | None:
        """Litry na osobu celkem."""
        rating = self.coordinator.rating
        return rating.volume_person if rating else None

    @property
    def extra_state_attributes(self) -> dict:
        """Rozpad na směsný a tříděný a období, za které to platí."""
        rating = self.coordinator.rating
        if not rating:
            return {}
        atributy: dict = {
            "smesny_l": rating.mixed_person,
            "tridene_l": rating.sorted_person,
        }
        if rating.period_from and rating.period_to:
            atributy["obdobi_od"] = rating.period_from.isoformat()
            atributy["obdobi_do"] = rating.period_to.isoformat()
        return atributy


class PeopleSensor(MojeOdpadkyEntity, SensorEntity):
    """Kolik osob je vedeno na stanovišti."""

    _attr_translation_key = "people"
    _attr_icon = "mdi:account-group"
    _attr_native_unit_of_measurement = "osob"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: MojeOdpadkyCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_people"

    @property
    def native_value(self) -> int | None:
        """Počet osob vedených na stanovišti."""
        return self.coordinator.people


class LastUpdateSensor(MojeOdpadkyEntity, SensorEntity):
    """Kdy naposledy vyšlo stažení dat ze serveru."""

    _attr_translation_key = "last_update"
    _attr_icon = "mdi:cloud-check-variant"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: MojeOdpadkyCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_last_update"

    @property
    def available(self) -> bool:
        """Zůstat dostupný i když poslední pokus selhal - právě pak je vidět."""
        return True

    @property
    def native_value(self) -> str | None:
        """Čas posledního úspěšného stažení: 20.09.2026 23:18.

        Naschvál jako text - časové razítko by Home Assistant vypsal půlkou
        slovy a půlkou číslicemi ("20. září 2026 v 23:18").
        """
        last = self.coordinator.last_success
        return last.strftime("%d.%m.%Y %H:%M") if last else None

    @property
    def extra_state_attributes(self) -> dict:
        """Strojový čas, jestli poslední pokus prošel a jak často se stahuje."""
        last = self.coordinator.last_success
        return {
            "cas": last.isoformat() if last else None,
            "posledni_pokus_uspesny": self.coordinator.last_update_success,
            "interval_hodin": round(
                self.coordinator.update_interval.total_seconds() / 3600
            )
            if self.coordinator.update_interval
            else None,
        }


def _slug(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    )
    return re.sub(r"[^a-z0-9]+", "_", ascii_value.lower()).strip("_")
