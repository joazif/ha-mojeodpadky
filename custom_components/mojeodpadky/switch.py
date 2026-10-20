"""Přepínače e-mailových upozornění po jednotlivých komoditách."""

from __future__ import annotations

import logging
import re

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from . import MojeOdpadkyConfigEntry
from .api import MojeOdpadkyError, Schedule, fingerprint, schedule_waste_type
from .const import DOMAIN
from .coordinator import MojeOdpadkyCoordinator
from .entity import MojeOdpadkyEntity

_LOGGER = logging.getLogger(__name__)

# Letopočet v entity_id přepínače ze starší verze ("..._2027").
RE_ROK = re.compile(r"(?:^|_)(?:19|20)\d{2,3}(?:_|$)")


def _komodity(coordinator: MojeOdpadkyCoordinator) -> dict[str, list[Schedule]]:
    """Sledované harmonogramy podle komodity: {"papír, plast": [...]}."""
    data = coordinator.data
    if not data:
        return {}
    skupiny: dict[str, list[Schedule]] = {}
    for item in data.schedules:
        if item.subscribed:
            komodita = schedule_waste_type(item, data.events)
            skupiny.setdefault(komodita.lower(), []).append(item)
    return skupiny


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MojeOdpadkyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Vytvořit přepínač pro každou sledovanou komoditu."""
    coordinator = entry.runtime_data
    _prevest_stare_prepinace(hass, entry, coordinator)
    known: set[str] = set()
    predpona = f"{entry.entry_id}_notify_"

    @callback
    def _sync() -> None:
        if not coordinator.data or not coordinator.last_update_success:
            return
        skupiny = _komodity(coordinator)

        nove = [
            NotificationSwitch(coordinator, entry.entry_id, klic)
            for klic in skupiny
            if klic not in known
        ]
        if nove:
            known.update(prepinac.klic for prepinac in nove)
            async_add_entities(nove)

        # Komodita, kterou už žádný sledovaný harmonogram nemá (loňský ročník
        # zmizel z webu, odběr se zrušil), by zůstala viset jako nedostupná.
        # Stránka bez jediného harmonogramu je spíš chyba čtení než skutečnost
        # - pak se nic nemaže.
        if not coordinator.data.schedules:
            return
        registr = er.async_get(hass)
        for zaznam in er.async_entries_for_config_entry(registr, entry.entry_id):
            unique_id = zaznam.unique_id or ""
            if zaznam.domain != "switch" or not unique_id.startswith(predpona):
                continue
            klic = unique_id[len(predpona):]
            if klic not in skupiny:
                known.discard(klic)
                registr.async_remove(zaznam.entity_id)
                _LOGGER.debug("Odstraněn přepínač %s bez harmonogramu", zaznam.entity_id)

    _sync()
    entry.async_on_unload(coordinator.async_add_listener(_sync))


def _prevest_stare_prepinace(
    hass: HomeAssistant,
    entry: MojeOdpadkyConfigEntry,
    coordinator: MojeOdpadkyCoordinator,
) -> None:
    """Převést přepínače ze starších verzí na klíč podle komodity.

    Starší verze je klíčovaly ID harmonogramu (to se mění každý rok) a pak
    "komoditou a místní částí" vyčtenou z názvu - jenže nové harmonogramy
    obec píše celé velkými písmeny a z názvu se komodita poznat nedá.
    Převod proběhne jen u přepínačů ve starém tvaru; když na jednu komoditu
    připadne víc starých, zůstane jeden. Entity_id s letopočtem se při tom
    jednou přejmenuje na čisté, když je volné.
    """
    data = coordinator.data
    if not data:
        return
    entry_id = entry.entry_id
    predpona = f"{entry_id}_notify_"
    registr = er.async_get(hass)
    stare = [
        zaznam
        for zaznam in er.async_entries_for_config_entry(registr, entry_id)
        if zaznam.domain == "switch"
        and (zaznam.unique_id or "").startswith(predpona)
        and _je_stary_klic((zaznam.unique_id or "")[len(predpona):])
    ]
    if not stare:
        return

    def komodita_pro(klic: str) -> str | None:
        for item in data.schedules:
            if (klic.isdigit() and item.schedule_id == int(klic)) or (
                not klic.isdigit() and fingerprint(item) == klic
            ):
                return schedule_waste_type(item, data.events)
        return None

    # Přepínače bez letopočtu v entity_id napřed - ty si ID nechají.
    stare.sort(key=lambda zaznam: bool(RE_ROK.search(zaznam.entity_id)))
    zarizeni = slugify(entry.title)
    for zaznam in stare:
        komodita = komodita_pro((zaznam.unique_id or "")[len(predpona):])
        nove = f"{predpona}{komodita.lower()}" if komodita else None
        if not nove or registr.async_get_entity_id("switch", DOMAIN, nove):
            # Harmonogram už na webu není, nebo jeho komoditu už zastupuje
            # jiný přepínač - starý by zůstal navždy nedostupný.
            registr.async_remove(zaznam.entity_id)
            _LOGGER.debug("Odstraněn starý přepínač %s", zaznam.entity_id)
            continue
        zmeny: dict = {"new_unique_id": nove}
        cile = f"switch.{zarizeni}_upozorneni_{slugify(komodita)}"
        if RE_ROK.search(zaznam.entity_id) and not registr.async_get(cile):
            zmeny["new_entity_id"] = cile
        registr.async_update_entity(zaznam.entity_id, **zmeny)
        _LOGGER.debug("Přepínač %s převeden na %s", zaznam.entity_id, nove)


def _je_stary_klic(klic: str) -> bool:
    """ID harmonogramu, nebo otisk "komodita|místní část" ze starší verze."""
    return klic.isdigit() or "|" in klic


class NotificationSwitch(MojeOdpadkyEntity, SwitchEntity):
    """E-mailová upozornění jedné komodity, jako tlačítko na webu.

    Nepatří konkrétnímu harmonogramu, ale komoditě tak, jak ji web píše u
    svozů ("Bio", "Papír, Plast"). Nový ročník harmonogramu tak ovládá
    pořád stejný přepínač; když jsou chvíli sledované oba ročníky (nebo dva
    harmonogramy téže komodity), přepíná se u všech.
    """

    _attr_icon = "mdi:email-alert-outline"

    def __init__(
        self,
        coordinator: MojeOdpadkyCoordinator,
        entry_id: str,
        klic: str,
    ) -> None:
        super().__init__(coordinator, entry_id)
        self.klic = klic
        self._attr_unique_id = f"{entry_id}_notify_{klic}"

    @property
    def _schedules(self) -> list[Schedule]:
        """Sledované harmonogramy této komodity, nejnovější první."""
        return sorted(
            _komodity(self.coordinator).get(self.klic, []),
            key=lambda item: item.schedule_id,
            reverse=True,
        )

    @property
    def name(self) -> str:
        """Jen komodita, jak ji píše web: "Upozornění: Papír, Plast"."""
        sledovane = self._schedules
        if not sledovane:
            return "Upozornění"
        return "Upozornění: " + schedule_waste_type(
            sledovane[0], self.coordinator.data.events
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
        """Celé názvy harmonogramů a ID odběrů.

        E-mail sem schválně nepatří: atributy vidí každý uživatel Home
        Assistantu a ukládají se do historie i záloh.
        """
        sledovane = self._schedules
        if not sledovane:
            return {}
        return {
            "harmonogram": ", ".join(item.name for item in sledovane),
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
