"""Senzory příštích svozů a odevzdaného odpadu."""

from __future__ import annotations

import re
import unicodedata
from datetime import date

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

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
from .api import belongs_to_current, fee_is_current, fee_year_for, points_value
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
        PeriodEndSensor(coordinator, entry.entry_id),
        CountTotalSensor(coordinator, entry.entry_id),
        CountPeriodSensor(coordinator, entry.entry_id),
        PeriodDaysLeftSensor(coordinator, entry.entry_id),
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

    known_counts: set[str] = set()

    @callback
    def _add_new_counts() -> None:
        # Všechny známé komodity, ne jen ty s letošním záznamem. Jinak by
        # po restartu na začátku nového roku vznikla jen entita pro to,
        # co se už odevzdalo, a ostatní by zůstaly "nedostupné".
        data = coordinator.data
        komodity: set[str] = set()
        if data:
            komodity.update(data.year_counts or {})
            komodity.update(data.points)
            if data.previous_counts:
                komodity.update(data.previous_counts[2])
        nove = [
            CommodityCountSensor(coordinator, entry.entry_id, komodita)
            for komodita in sorted(komodity)
            if komodita not in known_counts
        ]
        if nove:
            known_counts.update(sensor.komodita for sensor in nove)
            async_add_entities(nove)

    _add_new_counts()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_counts))

    async_add_entities(entities)


class NextCollectionSensor(MojeOdpadkyEntity, SensorEntity):
    """Nejbližší svoz bez ohledu na komoditu.

    Stav je český popisek (Dnes, Zítra, Za 5 dní), protože takhle to má být
    vidět v seznamu entit. Datum i počet dní jsou v atributech, automatizace
    se mají vázat na ně, ne na text.
    """

    _attr_translation_key = "next_collection"
    _attr_icon = "mdi:calendar-clock"
    _prepocitat_o_pulnoci = True

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

    _prepocitat_o_pulnoci = True

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
    _prepocitat_o_pulnoci = True

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
        """Kolik se bude platit na osobu po úlevě.

        Když poplatek patří k už uzavřenému MESOH roku (začátek nového
        roku, web má u nového "? Kč"), je stav neznámý. Ne nula: ta by
        se zapsala do statistik a v grafu vývoje ceny by byl každý říjen
        propad, který se nikdy nestal. Neznámý stav HA do grafu nepočítá.
        """
        fee = self.coordinator.fee
        if not fee or not fee_is_current(fee, self.coordinator.period):
            return None
        return fee.total

    @property
    def extra_state_attributes(self) -> dict:
        """Rok, sazba a úleva; u ještě neznámé ceny i loňský poplatek."""
        fee = self.coordinator.fee
        if not fee:
            return {}
        period = self.coordinator.period
        if not fee_is_current(fee, period):
            return {
                "rok": fee_year_for(period),
                "stav": "zatím nevyhodnoceno",
                "predchozi_rok": fee.year,
                "predchozi_poplatek": fee.total,
            }
        return {
            "rok": fee.year,
            "sazba": fee.rate,
            "uleva": fee.discount,
            "uleva_procent": fee.discount_percent,
        }


class CommodityCountSensor(MojeOdpadkyEntity, SensorEntity):
    """Kolikrát se komodita odevzdala v probíhajícím MESOH roce.

    Roste s každým odevzdáním a 1. října, kdy začíná nový MESOH rok,
    spadne na nulu - proto total_increasing, který s vynulováním počítá.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    # "51 ×" - kolikrát; sedí i na odevzdání na sběrném dvoře, kde o svoz
    # nejde, a na rozdíl od slova se nemusí skloňovat.
    _attr_native_unit_of_measurement = "×"

    def __init__(
        self, coordinator: MojeOdpadkyCoordinator, entry_id: str, komodita: str
    ) -> None:
        super().__init__(coordinator, entry_id)
        self.komodita = komodita
        self._attr_unique_id = f"{entry_id}_count_{_slug(komodita)}"
        self._attr_icon = ICONS.get(komodita, "mdi:counter")
        # Jen komodita, bez roku: období ukazuje řádek nad počty. HA u grafu
        # ukazuje aktuální název, takže s rokem by se loňský průběh jmenoval
        # letošním rokem; a ID se po vzniku nemění, rok by zastaral 1. října.
        self._attr_name = komodita
        self.entity_id = f"sensor.{_device_slug(coordinator)}_odevzdano_{_slug(komodita)}"

    @property
    def native_value(self) -> int | None:
        """Počet odevzdání; komodita, která letos ještě nebyla, má 0."""
        pocty = self.coordinator.data.year_counts if self.coordinator.data else None
        if pocty is None:
            return None
        return pocty.get(self.komodita, 0)

    @property
    def extra_state_attributes(self) -> dict:
        """Období a body za poslední odevzdání této komodity.

        Body bývaly samostatná entita; na stránce zařízení ale HA ukazuje
        i skryté entity, tak jsou tady. Nejnovější záznam se hledá při každém
        stažení na nástěnce i v tabulce za celý MESOH rok.
        """
        atributy: dict = {}
        obdobi = _obdobi(self.coordinator)
        if obdobi:
            atributy["obdobi_od"] = obdobi[0].isoformat()
            atributy["obdobi_do"] = obdobi[1].isoformat()

        zaznam = (
            self.coordinator.data.points.get(self.komodita)
            if self.coordinator.data
            else None
        )
        # Jen když se komodita letos už odevzdala - loňský záznam se
        # nesmí tvářit jako letošní.
        if zaznam and obdobi and not obdobi[0] <= zaznam.day <= obdobi[1]:
            zaznam = None
        if zaznam:
            atributy["eko_body"] = points_value(zaznam)
            atributy["posledni_odevzdani"] = zaznam.day.isoformat()
            atributy[ATTR_CONTAINER] = zaznam.container

        predchozi = self.coordinator.previous_counts
        if predchozi:
            od, do, pocty = predchozi
            atributy["predchozi_pocet"] = pocty.get(self.komodita, 0)
            atributy["predchozi_obdobi_od"] = od.isoformat()
            atributy["predchozi_obdobi_do"] = do.isoformat()
        return atributy


class CountTotalSensor(MojeOdpadkyEntity, SensorEntity):
    """Součet všech odevzdání v probíhajícím MESOH roce."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = "×"
    _attr_icon = "mdi:sigma"

    # Σ se v abecedním řazení dostane za všechna česká písmena, takže je
    # součet v diagnostice vždycky pod jednotlivými komoditami.
    _attr_name = "Σ Celkem"

    def __init__(self, coordinator: MojeOdpadkyCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_count_total"
        self.entity_id = f"sensor.{_device_slug(coordinator)}_odevzdano_celkem"

    @property
    def native_value(self) -> int | None:
        """Všechna odevzdání dohromady."""
        pocty = self.coordinator.data.year_counts if self.coordinator.data else None
        return sum(pocty.values()) if pocty is not None else None

    @property
    def extra_state_attributes(self) -> dict:
        """Z čeho se součet skládá, od nejčastější komodity."""
        pocty = self.coordinator.data.year_counts if self.coordinator.data else None
        atributy: dict = dict(sorted((pocty or {}).items(), key=lambda kv: -kv[1]))
        predchozi = self.coordinator.previous_counts
        if predchozi:
            od, do, minule = predchozi
            atributy["predchozi_celkem"] = sum(minule.values())
            atributy["predchozi_obdobi_od"] = od.isoformat()
            atributy["predchozi_obdobi_do"] = do.isoformat()
        return atributy


class CountPeriodSensor(MojeOdpadkyEntity, SensorEntity):
    """Za jaké období se počty odevzdání počítají.

    Nadpis nad počty v diagnostice: název je MESOH rok (2026/27), stav
    celé období. 1. října se přepne sám. Číslice se v abecedě řadí před
    písmena, takže je na stránce zařízení vždycky nahoře.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:calendar-range"

    def __init__(self, coordinator: MojeOdpadkyCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_count_period"
        self.entity_id = f"sensor.{_device_slug(coordinator)}_obdobi_odevzdani"

    @property
    def name(self) -> str:
        """MESOH rok, jak ho píše web: 2026/27."""
        obdobi = _obdobi(self.coordinator)
        if not obdobi:
            return "Období"
        return f"{obdobi[0].year}/{obdobi[1].year % 100:02d}"

    @property
    def native_value(self) -> str | None:
        """Období jako text: 01.10.2026 – 30.09.2027."""
        obdobi = _obdobi(self.coordinator)
        if not obdobi:
            return None
        return f"{obdobi[0]:%d.%m.%Y} – {obdobi[1]:%d.%m.%Y}"

    @property
    def extra_state_attributes(self) -> dict:
        """Strojové datumy a rok ve tvaru, jak ho píše web (2026/27)."""
        obdobi = _obdobi(self.coordinator)
        if not obdobi:
            return {}
        od, do = obdobi
        return {
            "od": od.isoformat(),
            "do": do.isoformat(),
            "rok": f"{od.year}/{do.year % 100:02d}",
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
        """Sazba, úleva v korunách, nebo úleva v procentech.

        Neznámá, dokud web nespočítá hodnoty pro probíhající rok - ze
        stejného důvodu jako u poplatku: nula by kazila graf.
        """
        fee = self.coordinator.fee
        if not fee or not fee_is_current(fee, self.coordinator.period):
            return None
        return getattr(fee, self._cast)

    @property
    def extra_state_attributes(self) -> dict:
        """Za který rok to platí."""
        fee = self.coordinator.fee
        if not fee:
            return {}
        period = self.coordinator.period
        if not fee_is_current(fee, period):
            return {"rok": fee_year_for(period), "stav": "zatím nevyhodnoceno"}
        return {"rok": fee.year}


def _skore_aktualni(coordinator: MojeOdpadkyCoordinator) -> bool:
    """Je skóre z nástěnky za probíhající MESOH rok?"""
    zobrazene = coordinator.shown_period
    return belongs_to_current(
        coordinator.period, zobrazene.date_from if zobrazene else None
    )


def _hodnoceni_aktualni(coordinator: MojeOdpadkyCoordinator) -> bool:
    """Je hodnocení stanoviště za probíhající MESOH rok?"""
    rating = coordinator.rating
    return belongs_to_current(
        coordinator.period, rating.period_from if rating else None
    )


def _predchozi(od: date | None, do: date | None, hodnota) -> dict:
    """Atributy s loňskou hodnotou, když letošní ještě není.

    Hodnota se neztrácí ani z grafu: dlouhodobé statistiky HA ji drží
    do chvíle, kdy senzor přešel na neznámý stav, a dál jen chybí body.
    """
    atributy: dict = {"stav": "zatím nevyhodnoceno", "predchozi_hodnota": hodnota}
    if od and do:
        atributy["predchozi_obdobi_od"] = od.isoformat()
        atributy["predchozi_obdobi_do"] = do.isoformat()
    return atributy


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
        """Body na osobu v probíhajícím MESOH roce; neznámé, než ho web vyhodnotí."""
        score = self.coordinator.score
        if not score or not _skore_aktualni(self.coordinator):
            return None
        return score.points

    @property
    def extra_state_attributes(self) -> dict:
        """Maximum a využití, nebo loňský výsledek, když letošní ještě není."""
        score = self.coordinator.score
        if not score:
            return {}
        zobrazene = self.coordinator.shown_period
        if not _skore_aktualni(self.coordinator):
            atributy = _predchozi(
                zobrazene.date_from, zobrazene.date_to, score.points
            )
            atributy["predchozi_maximum"] = score.max_points
            return atributy
        atributy: dict = {"maximum": score.max_points, "vyuziti_procent": score.percent}
        if zobrazene:
            atributy["obdobi_od"] = zobrazene.date_from.isoformat()
            atributy["obdobi_do"] = zobrazene.date_to.isoformat()
        return atributy


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
        """Využití potenciálu v probíhajícím roce; neznámé, než ho web vyhodnotí."""
        score = self.coordinator.score
        if not score or not _skore_aktualni(self.coordinator):
            return None
        return score.percent

    @property
    def extra_state_attributes(self) -> dict:
        """Body, ze kterých se procento počítá, nebo loňský výsledek."""
        score = self.coordinator.score
        if not score:
            return {}
        if not _skore_aktualni(self.coordinator):
            zobrazene = self.coordinator.shown_period
            return _predchozi(zobrazene.date_from, zobrazene.date_to, score.percent)
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
        """Litry na osobu v probíhajícím roce; neznámé, než ho web vyhodnotí."""
        rating = self.coordinator.rating
        if not rating or not _hodnoceni_aktualni(self.coordinator):
            return None
        return rating.volume_person

    @property
    def extra_state_attributes(self) -> dict:
        """Rozpad na směsný a tříděný, nebo loňský výsledek."""
        rating = self.coordinator.rating
        if not rating:
            return {}
        if not _hodnoceni_aktualni(self.coordinator):
            atributy = _predchozi(
                rating.period_from, rating.period_to, rating.volume_person
            )
            atributy["predchozi_smesny_l"] = rating.mixed_person
            atributy["predchozi_tridene_l"] = rating.sorted_person
            return atributy
        atributy: dict = {
            "smesny_l": rating.mixed_person,
            "tridene_l": rating.sorted_person,
        }
        if rating.period_from and rating.period_to:
            atributy["obdobi_od"] = rating.period_from.isoformat()
            atributy["obdobi_do"] = rating.period_to.isoformat()
        return atributy


class PeriodEndSensor(MojeOdpadkyEntity, SensorEntity):
    """Kdy končí MESOH rok - body se sbírají od 1. 10. do 30. 9."""

    _attr_translation_key = "period_end"
    _attr_icon = "mdi:calendar-end"
    _attr_device_class = SensorDeviceClass.DATE
    _prepocitat_o_pulnoci = True

    def __init__(self, coordinator: MojeOdpadkyCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_period_end"

    @property
    def native_value(self) -> date | None:
        """Poslední den probíhajícího MESOH roku."""
        obdobi = _obdobi(self.coordinator)
        return obdobi[1] if obdobi else None

    @property
    def extra_state_attributes(self) -> dict:
        """Začátek období a kolik dní zbývá."""
        obdobi = _obdobi(self.coordinator)
        if not obdobi:
            return {}
        return {
            "zacatek": obdobi[0].isoformat(),
            "zbyva_dni": (obdobi[1] - dt_today()).days,
        }


class PeriodDaysLeftSensor(MojeOdpadkyEntity, SensorEntity):
    """Kolik dní zbývá do konce MESOH roku - číslo, na které jde automatizace.

    Text typu "Za 6 dní" by se číst dal, ale podmínka "méně než 14 dní"
    by na něm postavit nešla. Proto je to samostatná entita s číslem.
    """

    _attr_translation_key = "period_days_left"
    _attr_icon = "mdi:timer-sand"
    _attr_native_unit_of_measurement = "dní"
    _prepocitat_o_pulnoci = True

    def __init__(self, coordinator: MojeOdpadkyCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_period_days_left"

    @property
    def native_value(self) -> int | None:
        """Dny do konce MESOH roku; v poslední den 0."""
        obdobi = _obdobi(self.coordinator)
        return (obdobi[1] - dt_today()).days if obdobi else None

    @property
    def extra_state_attributes(self) -> dict:
        """Datum konce, ať je vidět, k čemu se odpočítává."""
        obdobi = _obdobi(self.coordinator)
        if not obdobi:
            return {}
        konec = obdobi[1]
        return {
            "konec": konec.isoformat(),
            "konec_text": f"{konec.day}. {konec.month}. {konec.year}",
        }


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
    """Kdy naposledy vyšlo stažení dat ze serveru.

    Jmenuje se "Aktualizováno": v diagnostice se řadí podle abecedy a to
    je hned pod MESOH rokem, nad komoditami - ne někde mezi nimi.
    """

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


def _obdobi(coordinator: MojeOdpadkyCoordinator):
    """(začátek, konec) probíhajícího MESOH období.

    Primárně ze seznamu období na nástěnce - to se 1. října přepne samo.
    Hodnocení je jen záloha: web ho po přihlášení ukazuje za poslední
    vyhodnocený rok, tedy na začátku nového roku za ten loňský.
    """
    if coordinator.period:
        return coordinator.period.date_from, coordinator.period.date_to
    rating = coordinator.rating
    if rating and rating.period_from and rating.period_to:
        return rating.period_from, rating.period_to
    return None


def _device_slug(coordinator: MojeOdpadkyCoordinator) -> str:
    """Začátek entity_id podle zařízení: "Nová Lhota" -> nova_lhota.

    Stejný slugify jako v migraci v __init__.py, aby nové entity i ty
    přejmenované skončily na úplně stejném ID.
    """
    if coordinator.entry is not None:
        return slugify(coordinator.entry.title)
    return slugify(coordinator.client.town or coordinator.client.slug or "odpadky")


def _slug(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    )
    return re.sub(r"[^a-z0-9]+", "_", ascii_value.lower()).strip("_")
