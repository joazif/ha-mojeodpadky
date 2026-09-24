"""Aktualizace dat z mojeodpadky.cz."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    CollectedItem,
    CollectionEvent,
    Fee,
    MojeOdpadkyClient,
    MojeOdpadkyError,
    Rating,
    Schedule,
    Score,
    count_by_type,
    diff_collected,
    find_successor,
    fingerprint,
    latest_points,
    page_text,
)
from .const import (
    ATTR_CONTAINER,
    CONF_SCHEDULES,
    ATTR_DATE,
    ATTR_WASTE_TYPE,
    COLLECTED_LIMIT,
    COLLECTED_PAGE_SIZE,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DOMAIN,
    EVENT_COLLECTED,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class MojeOdpadkyData:
    """Data jednoho obnovení."""

    events: list[CollectionEvent]
    schedules: list[Schedule]
    email: str = ""
    people: int | None = None
    collected: list[CollectedItem] = field(default_factory=list)
    collected_total: int | None = None
    fee: Fee | None = None
    score: Score | None = None
    rating: Rating | None = None
    # Body za poslední odevzdání každé komodity: {"Plast": záznam, ...}
    points: dict[str, CollectedItem] = field(default_factory=dict)
    # Kolikrát se která komodita odevzdala v probíhajícím MESOH roce;
    # None, dokud se hodnocení ani jednou nestáhlo.
    year_counts: dict[str, int] | None = None


class MojeOdpadkyCoordinator(DataUpdateCoordinator[MojeOdpadkyData]):
    """Stahuje svozový kalendář, nástěnku a hlídá, že odběry odpovídají výběru."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: MojeOdpadkyClient,
        selected: set[int],
        scan_interval_hours: int = DEFAULT_SCAN_INTERVAL_HOURS,
        entry_id: str = "",
        entry=None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=scan_interval_hours),
        )
        self.client = client
        self.selected = selected
        self.entry = entry
        # Poslední výběr, který integrace na web skutečně promítla. Drží se
        # na disku, aby po restartu nevypadal cizí stav webu jako změna.
        self._store: Store = Store(hass, 1, f"{DOMAIN}_{entry_id}_selection")
        self._applied: set[int] | None = None
        # Otisky vybraných harmonogramů pro přelom roku: {id: "papír|nová"}
        self._fingerprints: dict[int, str] = {}
        self.last_success: datetime | None = None
        # Hodnocení stanoviště má 0,7 MB a mění se, jen když přibude svoz.
        # Stahuje se proto po novém záznamu, nebo nejvýš jednou za den.
        self._heavy_at: datetime | None = None
        # Záznamy za celý MESOH rok z hodnocení; drží se mezi obnoveními,
        # protože se hodnocení nestahuje pokaždé.
        self._year_records: list[CollectedItem] | None = None

    async def _async_update_data(self) -> MojeOdpadkyData:
        # Kalendář se stahuje jednou a stránka se pak podává dál; dřív si ji
        # tahal zvlášť koordinátor i srovnání odběrů.
        try:
            body = await self.client.async_fetch_page()
        except MojeOdpadkyError as err:
            raise UpdateFailed(str(err)) from err

        schedules = self.client.parse_schedules(body)

        # Přelom roku se řeší dřív než odběry, ať se letošní harmonogram
        # přihlásí hned a ne až za další interval.
        if await self._async_follow_year_change(schedules):
            body = await self.client.async_fetch_page()
            schedules = self.client.parse_schedules(body)

        odhlasit = await self._async_selection_changed()

        try:
            nove_telo = await self.client.async_apply_selection(
                self.selected, odhlasit, body
            )
        except MojeOdpadkyError as err:
            raise UpdateFailed(str(err)) from err

        if nove_telo is not body:
            # Něco se přihlásilo nebo odhlásilo, stránka je čerstvá.
            body = nove_telo
            schedules = self.client.parse_schedules(body)
        email = self.client.parse_default_email(body)

        if odhlasit:
            await self._async_remember_selection()

        if self.client.town is None:
            # Veřejná stránka obce, jeden GET za běh - název do jména zařízení.
            await self.client.async_fetch_town()

        collected, total, fee, score = await self._async_collected()

        # Rozdíl se počítá jednou: řekne, jestli se vyplatí sáhnout
        # na velké stránky, a zároveň co ohlásit automatizacím.
        nove = (
            diff_collected(self.data.collected, collected) if self.data else []
        )
        rating, people = await self._async_heavy_pages(bool(nove))
        self._fire_new_collected(nove)
        points = self._latest_points(collected)
        year_counts = (
            count_by_type(self._year_records)
            if self._year_records is not None
            else None
        )

        self.last_success = dt_now()

        return MojeOdpadkyData(
            events=self.client.parse_events(body),
            schedules=schedules,
            email=email,
            people=people,
            collected=collected,
            collected_total=total,
            fee=fee,
            score=score,
            rating=rating,
            points=points,
            year_counts=year_counts,
        )

    async def _async_collected(
        self,
    ) -> tuple[list[CollectedItem], int | None, Fee | None, Score | None]:
        """Stáhnout nástěnku. Výpadek nástěnky nesmí shodit celou integraci."""
        try:
            body = await self.client.async_fetch_collected(COLLECTED_PAGE_SIZE)
        except MojeOdpadkyError as err:
            _LOGGER.debug("Nástěnku se nepodařilo stáhnout: %s", err)
            if self.data:
                return self.data.collected, None, self.data.fee, self.data.score
            return [], None, None, None

        # Tři ze čtyř parserů čtou stránku bez značek; převede se jednou.
        text = page_text(body)
        items = self.client.parse_collected(body)[:COLLECTED_LIMIT]
        total = self.client.parse_collected_total(body, text)
        fee = self.client.parse_fee(body, text)
        score = self.client.parse_score(body, text)

        if not items:
            _LOGGER.debug("Na nástěnce nejsou žádné záznamy o svezeném odpadu")

        return items, total, fee, score

    async def _async_heavy_pages(
        self, nove_zaznamy: bool
    ) -> tuple[Rating | None, int | None]:
        """Hodnocení stanoviště a inventura - dohromady skoro megabajt.

        Obojí se mění jen tehdy, když přibude svoz. Stahuje se proto při
        prvním načtení, po novém záznamu na nástěnce a jinak nejvýš jednou
        za den, aby se web zbytečně nezatěžoval.
        """
        stare = self._heavy_at is None or dt_now() - self._heavy_at >= timedelta(days=1)
        if not (self.data is None or nove_zaznamy or stare):
            return self.data.rating, self.data.people

        rating = await self._async_rating()
        people = await self._async_people()
        self._heavy_at = dt_now()
        return rating, people

    async def _async_follow_year_change(self, schedules: list[Schedule]) -> bool:
        """Přenést výběr na letošní harmonogramy, když ty loňské zmizely.

        Obec každý rok vypíše nové harmonogramy s novými ID a staré ze
        stránky zmizí. Výběr uložený v nastavení by pak ukazoval do prázdna,
        proto se hledá nástupce podle komodity a místní části.
        """
        znama = {item.schedule_id for item in schedules}
        chybejici = self.selected - znama

        # Otisky se průběžně doplňují, dokud harmonogramy na stránce jsou.
        pred = dict(self._fingerprints)
        for item in schedules:
            if item.schedule_id in self.selected:
                self._fingerprints[item.schedule_id] = fingerprint(item)
        if self._fingerprints != pred and self._applied is not None:
            await self._async_save_state()

        if not chybejici:
            return False

        novy_vyber = set(self.selected)
        prevedeno: dict[int, int] = {}
        ztraceno: list[int] = []

        for stare in sorted(chybejici):
            otisk = self._fingerprints.get(stare)
            nastupce = (
                find_successor(otisk, schedules, novy_vyber) if otisk else None
            )
            if nastupce is None:
                ztraceno.append(stare)
                continue
            novy_vyber.discard(stare)
            novy_vyber.add(nastupce)
            prevedeno[stare] = nastupce

        if ztraceno:
            _LOGGER.warning(
                "Harmonogramy %s už na webu nejsou a nástupce se nenašel; "
                "zkontrolujte výběr v nastavení integrace",
                ztraceno,
            )

        if not prevedeno:
            return False

        _LOGGER.info("Přelom roku: harmonogramy převedené na nové %s", prevedeno)
        self.selected = novy_vyber
        # Otisky nepřevedených harmonogramů musí zůstat, jinak by se při
        # dalším přelomu roku neměly podle čeho hledat.
        for stare, nove in prevedeno.items():
            self._fingerprints[nove] = self._fingerprints.pop(stare)
        # Ať to není vidět jako uživatelova změna - jinak by se odhlašovalo.
        await self._async_remember_selection()

        if self.entry is not None:
            self.hass.config_entries.async_update_entry(
                self.entry,
                options={
                    **self.entry.options,
                    CONF_SCHEDULES: [str(item) for item in sorted(novy_vyber)],
                },
            )

        return True

    async def _async_selection_changed(self) -> bool:
        """Změnil uživatel výběr harmonogramů v Home Assistantu?

        Odhlašuje se jen tehdy. Kdyby se odhlašovalo při každém obnovení,
        stačí jediný rozejitý stav (ruční změna na webu, nová ID po přelomu
        roku, čerstvá instalace) a integrace smaže odběr, o který uživatel
        nepřišel dobrovolně. Tohle se jednou stalo a je to nevratné.
        """
        if self._applied is None:
            ulozeno = await self._store.async_load()
            if ulozeno is None:
                # První běh: co je na webu, to platí. Jen si výběr zapamatuj.
                await self._async_remember_selection()
                return False
            self._applied = {int(item) for item in ulozeno.get("schedules", [])}
            self._fingerprints = {
                int(klic): hodnota
                for klic, hodnota in (ulozeno.get("fingerprints") or {}).items()
            }

        return self.selected != self._applied

    async def _async_remember_selection(self) -> None:
        """Zapsat výběr jako promítnutý na web."""
        self._applied = set(self.selected)
        await self._async_save_state()

    async def _async_save_state(self) -> None:
        """Uložit výběr i otisky.

        Otisky musí přežít restart: přelom roku se pozná tak, že vybrané ID
        na stránce chybí, a bez otisku není podle čeho hledat nástupce.
        Restart mezi dvěma ročníky je běžná věc, ne výjimka.
        """
        await self._store.async_save(
            {
                "schedules": sorted(self._applied or set()),
                "fingerprints": {
                    str(klic): hodnota
                    for klic, hodnota in sorted(self._fingerprints.items())
                },
            }
        )

    async def _async_people(self) -> int | None:
        """Aktuální počet osob z inventury stanoviště."""
        try:
            body = await self.client.async_fetch_inventory()
        except MojeOdpadkyError as err:
            _LOGGER.debug("Inventuru se nepodařilo stáhnout: %s", err)
            return self.data.people if self.data else None

        return self.client.parse_people(body)

    async def _async_rating(self) -> Rating | None:
        """Hodnocení stanoviště. Stránka je velká, výpadek nic neshodí."""
        try:
            body = await self.client.async_fetch_rating()
        except MojeOdpadkyError as err:
            _LOGGER.debug("Hodnocení stanoviště se nepodařilo stáhnout: %s", err)
            return self.data.rating if self.data else None

        # Když se stránka stahuje, vezmou se z ní i záznamy za celý rok -
        # je to jediný zdroj bodů u komodit, které se odevzdávají zřídka.
        zaznamy = self.client.parse_rating_records(body)
        if zaznamy is not None:
            # I prázdný seznam platí: nový MESOH rok, počty jdou na nulu.
            self._year_records = zaznamy
        return self.client.parse_rating(body)

    def _latest_points(
        self, collected: list[CollectedItem]
    ) -> dict[str, CollectedItem]:
        """Body za poslední odevzdání každé komodity.

        Nejnovější záznam se hledá při každém obnovení na nástěnce (nejčerstvější
        data) i v záznamech za celý rok (komodity, které v posledních dvaceti
        nejsou). Komodita, která ze stránek zmizí - třeba po začátku nového
        MESOH roku - si drží poslední známou hodnotu, ať graf nespadne do prázdna.
        """
        nove = latest_points(collected, self._year_records or [])
        dosavadni = dict(self.data.points) if self.data else {}
        for komodita, item in nove.items():
            stary = dosavadni.get(komodita)
            if stary is None or item.day >= stary.day:
                dosavadni[komodita] = item
        return dosavadni

    def _fire_new_collected(self, nove: list[CollectedItem]) -> None:
        """Vyvolat událost pro každý záznam, který na nástěnce přibyl."""
        for item in nove:
            _LOGGER.debug("Nový záznam na nástěnce: %s", item)
            self.hass.bus.async_fire(
                EVENT_COLLECTED,
                {
                    ATTR_DATE: item.day.isoformat(),
                    ATTR_WASTE_TYPE: item.waste_type,
                    ATTR_CONTAINER: item.container,
                    "ekobody": item.points,
                    # Při víc účtech musí automatizace poznat, čí záznam to je.
                    "ucet": self.entry.title if self.entry else self.client.slug,
                    "entry_id": self.entry.entry_id if self.entry else None,
                },
            )

    @property
    def waste_types(self) -> list[str]:
        """Komodity, pro které máme aspoň jeden svoz."""
        if not self.data:
            return []
        return sorted({event.waste_type for event in self.data.events})

    @property
    def email(self) -> str:
        """E-mail, který má uživatel vyplněný na webu."""
        return self.data.email if self.data else ""

    @property
    def fee(self) -> Fee | None:
        """Předpokládaný poplatek za odpady na příští rok."""
        return self.data.fee if self.data else None

    @property
    def people(self) -> int | None:
        """Počet osob na stanovišti podle inventury."""
        if self.data and self.data.people is not None:
            return self.data.people
        rating = self.rating
        return rating.people if rating else None

    @property
    def rating(self) -> Rating | None:
        """Objem a osoby z Hodnocení stanoviště."""
        return self.data.rating if self.data else None

    @property
    def score(self) -> Score | None:
        """Skóre motivačního systému MESOH."""
        return self.data.score if self.data else None

    @property
    def collected(self) -> list[CollectedItem]:
        """Poslední odevzdání, nejnovější první."""
        if not self.data:
            return []
        return self.data.collected

    def next_event(self, waste_type: str | None = None) -> CollectionEvent | None:
        """Nejbližší svoz jedním průchodem, bez stavění seznamu.

        Senzory se na něj ptají při každé změně stavu, a událostí je přes
        sto na rok.
        """
        if not self.data:
            return None
        today = dt_today()
        for event in self.data.events:
            if event.day >= today and (
                waste_type is None or event.waste_type == waste_type
            ):
                return event
        return None

    def upcoming(self, waste_type: str | None = None) -> list[CollectionEvent]:
        """Svozy ode dneška dál, volitelně jen pro jednu komoditu."""
        if not self.data:
            return []
        today = dt_today()
        return [
            event
            for event in self.data.events
            if event.day >= today
            and (waste_type is None or event.waste_type == waste_type)
        ]


def dt_today() -> date:
    """Dnešní datum v lokální zóně."""
    return dt_util.now().date()


def dt_now() -> datetime:
    """Teď, v lokální zóně."""
    return dt_util.now()
