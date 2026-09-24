"""API klient pro mojeodpadky.cz.

Stránka svozového kalendáře nese kompletní seznam svozů v atributu
``data-events`` elementu ``#collectionScheduleCalendar`` (JSON pro FullCalendar),
takže na stažení celého roku stačí jediný GET s přihlášenou session.

Nástěnka ``/{slug}/nastenka`` nese historii skutečně svezeného odpadu
v obyčejné HTML tabulce, stránkované přes query parametry (žádný AJAX).

Přihlašování i přepínání odběrů jedou jako obyčejné POSTy bez CSRF tokenu,
ověřuje se pouze session cookie.
"""

from __future__ import annotations

import asyncio
import html as html_lib
import json
import logging
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date

import aiohttp

_LOGGER = logging.getLogger(__name__)

BASE = "https://www.mojeodpadky.cz"
USER_AGENT = "Mozilla/5.0 (compatible; HomeAssistant mojeodpadky)"
TIMEOUT = aiohttp.ClientTimeout(total=45)

RE_EVENTS = re.compile(
    r'id="collectionScheduleCalendar"[^>]*?\sdata-events="([^"]*)"'
)
RE_SIGNIN = re.compile(r'id="frm-signInForm"')
RE_TITLE = re.compile(r'm-portlet__head-text"\s*>\s*(.*?)\s*</h3>', re.S)
RE_SUBSCRIBE = re.compile(r'js-subscribe-form[^>]*?data-id="(\d+)"')
RE_UNSUBSCRIBE = re.compile(r'scheduleId=(\d+)&(?:amp;)?do=Unsubscribe')
RE_NOTIFY_ID = re.compile(r'js-notification-form[^>]*?data-id="(\d+)"')
# Odkaz "Vypnout upozornění" je na kartě jen tehdy, když jsou zapnutá -
# je to zároveň nejspolehlivější příznak stavu i zdroj ID odběru.
RE_NOTIFY_OFF = re.compile(r"subscribeId=(\d+)&(?:amp;)?do=NotificationOff")
RE_RANGE = re.compile(
    r"od\s*<span[^>]*>(\d{2}\.\d{2}\.\d{4})</span>\s*do\s*"
    r"<span[^>]*>(\d{2}\.\d{2}\.\d{4})</span>",
    re.S,
)
RE_EMAIL = re.compile(r'name="email"[^>]*?value="([^"]*)"')
# Karta hlásí stav e-mailových upozornění textem "E-mail upozornění: vypnuty",
# při zapnutých je tam místo toho adresa.
RE_NOTIFY_STATE = re.compile(
    r"E-mail upozornění:\s*<span[^>]*>\s*(.*?)\s*</span>", re.S
)
RE_SLUG_PATH = re.compile(r"^/([a-z0-9-]+)/")
# Odkaz na stránku obce v přihlášeném webu - druhá cesta ke slugu,
# když po přihlášení server zůstane na homepage.
RE_SLUG_LINK = re.compile(
    r'href="(?:https://www\.mojeodpadky\.cz)?/([a-z0-9-]{2,})/'
    r'(?:svozovy-kalendar|nastenka|sberna-mista|moje-nadoby)'
)
# Přihlášený web má někde odhlášení; slouží jako pojistka, kdyby se
# přihlašovací formulář renderoval i přihlášenému uživateli.
RE_SIGNOUT = re.compile(r"do=signOut|/odhlasit|Odhlásit", re.I)
RE_PAGE_TITLE = re.compile(r"<title>(.*?)</title>", re.S | re.I)
# Titulek stránky obce je "Aktuality Nová Lhota | Moje odpadky".
# Za svislítkem je vždycky název webu, před názvem obce jméno stránky.
TITLE_PAGE_LABELS = (
    "Aktuality",
    "Nástěnka",
    "Svozový kalendář",
    "Moje nádoby",
    "Sběrná místa",
)
RE_TAG = re.compile(r"<[^>]+>")
# Karta harmonogramu je <div class="m-portlet ...>; vnorene m-portlet__head
# a m-portlet__body maji stejny prefix, proto je v rozdeleni odlisujeme
# znakem za "m-portlet".
RE_CARD_SPLIT = re.compile(r'(?=<div class="m-portlet[ "])')

# Nástěnka: tabulka svezeného odpadu. Hledá se podle hlavičky, ne podle
# pořadí - tabulky jsou na stránce tři a ta naše je druhá.
RE_TABLE = re.compile(r"<table\b.*?</table>", re.S | re.I)
RE_ROW = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S | re.I)
RE_CELL = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.S | re.I)
RE_CZ_DATE = re.compile(r"^\d{1,2}\.\s*\d{1,2}\.\s*\d{4}$")
# "Zobrazeno 10 ze 747 záznamů" - mezi čísly a slovy bývají tagy,
# hledá se proto až v textu bez značek.
RE_TOTAL = re.compile(r"ze\s+([\d\s\u00a0]+?)\s*z[áa]znam", re.I)


# "Celkem EKO bodů/osoba 33.5 z 110.5" a "využíváte na 30.3 %" - volný text
# s nedělitelnými mezerami, čte se ze stránky bez značek.
# Stránka Hodnocení stanoviště: "Celkový obsloužený objem/osoba 5753 litrů
# SKO : 807,4 l , TO : 4945,6 l" a řádek s počty osob po měsících.
RE_VOLUME = re.compile(
    r"Celkový obsloužený objem\s*/\s*osoba\s*([\d\s.,]+?)\s*litrů"
    r"(?:\s*SKO\s*:\s*([\d\s.,]+?)\s*l)?"
    r"(?:\s*,\s*TO\s*:\s*([\d\s.,]+?)\s*l)?",
    re.I,
)
RE_PERIOD = re.compile(
    r"Období:\s*(\d{1,2}\.\d{1,2}\.\d{4})\s*-\s*(\d{1,2}\.\d{1,2}\.\d{4})"
)
RE_PEOPLE = re.compile(r"Počet osob na stanovišti\s*((?:\d+\s+)*\d+)")
# Inventura stanoviště: aktuální počet osob. Tabulka v hodnocení je
# po měsících a zaostává, tohle je stav teď.
RE_PEOPLE_NOW = re.compile(r"Počet osob\s+(\d+)")
RE_SCORE = re.compile(
    r"Celkem EKO bodů\s*/\s*osoba\s*([\d.,]+)\s*z\s*([\d.,]+)", re.I
)
RE_SCORE_PERCENT = re.compile(r"využíváte na\s*([\d.,]+)\s*%", re.I)
RE_FEE_YEAR = re.compile(r"Poplatek za odpady na rok\s*(\d{4})", re.I)
RE_FEE_RATE = re.compile(r"sazba poplatku na osobu:\s*([\d\s]+)\s*Kč", re.I)
RE_FEE_DISCOUNT = re.compile(
    r"úleva MESOH z poplatku na osobu:\s*([\d\s]+)\s*Kč\s*\(\s*([\d.,]+)\s*%", re.I
)
RE_FEE_TOTAL = re.compile(
    r"po odečtení úlevy MESOH na osobu:\s*([\d\s]+)\s*Kč", re.I
)


class MojeOdpadkyError(Exception):
    """Obecná chyba komunikace se serverem."""


class InvalidAuth(MojeOdpadkyError):
    """Neplatné přihlašovací údaje."""


class SlugNotFound(MojeOdpadkyError):
    """Nepodařilo se zjistit adresu obce."""


@dataclass(slots=True)
class Schedule:
    """Jeden harmonogram svozu."""

    schedule_id: int
    name: str
    subscribed: bool
    subscribe_id: int | None = None
    notifications: bool = False
    date_from: date | None = None
    date_to: date | None = None

    @property
    def short_name(self) -> str:
        """Jen komodita: "Harmonogram papír NOVÁ LHOTA + ZÁHOŘÍ 2026" -> "Papír".

        Bere slova do prvního, které je celé velkými písmeny (místní část)
        nebo je to letopočet.
        """
        slova = self.name.split()
        if slova and slova[0].lower() == "harmonogram":
            slova = slova[1:]

        vybrane: list[str] = []
        for slovo in slova:
            ocesane = slovo.strip("+-,")
            if ocesane.isdigit() or (ocesane.isupper() and len(ocesane) > 1):
                break
            vybrane.append(slovo)

        text = " ".join(vybrane) or self.name
        return text[:1].upper() + text[1:]

    @property
    def area(self) -> str:
        """Místní část: "bioodpad ZÁHOŘÍ 2026" -> "Záhoří".

        Bere první slovo psané velkými písmeny; to je v názvech harmonogramů
        vždycky místní část. Když tam žádné není, vrátí prázdný řetězec.
        """
        for slovo in self.name.split():
            ocesane = slovo.strip("+-,")
            if ocesane.isupper() and len(ocesane) > 1 and not ocesane.isdigit():
                return ocesane.capitalize()
        return ""

    @property
    def label(self) -> str:
        """Popisek do výběru v config flow.

        Na jeden řádek se toho vejde málo, proto pryč se slovem "Harmonogram"
        na začátku (má ho každý) a datumy nakrátko: "5.1.-28.12.2026".
        """
        name = self.name
        for prefix in ("Harmonogram ", "harmonogram "):
            if name.startswith(prefix):
                name = name[len(prefix):]
                break
        name = name[:1].upper() + name[1:]

        if not (self.date_from and self.date_to):
            return name

        start = f"{self.date_from.day}.{self.date_from.month}."
        end = f"{self.date_to.day}.{self.date_to.month}.{self.date_to.year}"
        if self.date_from.year != self.date_to.year:
            start = f"{start}{self.date_from.year}"
        return f"{name}  ·  {start}-{end}"


@dataclass(slots=True)
class CollectionEvent:
    """Jeden svoz."""

    day: date
    waste_type: str
    schedule_name: str


@dataclass(slots=True)
class CollectedItem:
    """Jeden záznam z nástěnky - co se skutečně svezlo nebo odevzdalo."""

    day: date
    waste_type: str
    container: str
    points: str = ""

    @property
    def key(self) -> tuple:
        """Identita záznamu pro porovnání dvou obnovení."""
        return (self.day, self.waste_type, self.container)


@dataclass(slots=True)
class Rating:
    """Čísla ze stránky Hodnocení stanoviště za probíhající MESOH rok."""

    volume_person: float
    mixed_person: float | None = None
    sorted_person: float | None = None
    people: int | None = None
    period_from: date | None = None
    period_to: date | None = None


@dataclass(slots=True)
class Score:
    """Skóre motivačního systému MESOH na osobu."""

    points: float
    max_points: float
    percent: float


@dataclass(slots=True)
class Fee:
    """Předpokládaný poplatek za odpady na příští rok."""

    year: int
    rate: int
    discount: int
    discount_percent: float
    total: int


def _parse_cz_date(value: str) -> date | None:
    """Datum ve tvaru 5.1.2026. Nesmysl vrací None, ne výjimku."""
    try:
        day, month, year = (int(part) for part in value.split("."))
        return date(year, month, day)
    except ValueError:
        # Buď to nejsou tři čísla, nebo je to neexistující datum (31.2.).
        return None


def _strip_tags(value: str) -> str:
    return html_lib.unescape(RE_TAG.sub("", value)).strip()


def _cell_text(value: str) -> str:
    """Text buňky tabulky se srovnanými mezerami a bez nedělitelných mezer."""
    return " ".join(_strip_tags(value).replace("\u00a0", " ").split())


def page_text(body: str) -> str:
    """Stránka bez značek, entit a nedělitelných mezer.

    Na nástěnce z toho čtou čtyři parsery naráz. Když si výsledek předají,
    udělá se práce jednou; u hodnocení stanoviště jde o 0,7 MB, takže to
    není zanedbatelné.
    """
    return " ".join(
        html_lib.unescape(RE_TAG.sub(" ", body)).replace("\u00a0", " ").split()
    )


def fingerprint(item: Schedule) -> str:
    """Otisk harmonogramu, který přežije přelom roku.

    ID se každý rok mění, komodita a místní část ne. Letopočet se z názvu
    vynechává právě proto, že je to ta měnící se část.
    """
    return f"{item.short_name.lower()}|{item.area.lower()}"


def find_successor(
    otisk: str, current: list[Schedule], taken: set[int]
) -> int | None:
    """Letošní obdoba harmonogramu, jehož ID už na webu není."""
    for item in current:
        if item.schedule_id in taken:
            continue
        if fingerprint(item) == otisk:
            return item.schedule_id
    return None


def distinguish(item: Schedule, others: list[Schedule]) -> str:
    """Čím se harmonogram liší od ostatních se stejnou komoditou.

    Názvy harmonogramů si každá obec píše po svém, takže se nespoléhá na
    jeden vzorec. Postupuje se od nejhezčího k nejspolehlivějšímu:

    1. místní část psaná velkými písmeny (``ZÁHOŘÍ`` -> ``Záhoří``),
    2. první slovo, které ostatní harmonogramy nemají - typicky letopočet
       u starého a nového harmonogramu téže komodity,
    3. ID harmonogramu, což je vždycky jedinečné.
    """
    if not others:
        return ""

    oblasti = {other.area for other in others}
    if item.area and item.area not in oblasti:
        return item.area

    cizi: set[str] = set()
    for other in others:
        cizi.update(slovo.lower() for slovo in other.name.split())

    for slovo in item.name.split():
        ocesane = slovo.strip("+-,()")
        if len(ocesane) > 1 and ocesane.lower() not in cizi:
            return ocesane.capitalize() if ocesane.isupper() else ocesane

    return str(item.schedule_id)


def diff_collected(
    old: list[CollectedItem], new: list[CollectedItem]
) -> list[CollectedItem]:
    """Záznamy, které na nástěnce přibyly od minulého stažení.

    Porovnává se jako multimnožina - v jeden den může být stejná komodita
    odevzdaná víckrát a i ten druhý záznam je nový. Bez předchozích dat
    se nevrací nic; při prvním stažení nemá smysl hlásit celou historii.
    """
    if not old or not new:
        return []

    added = Counter(item.key for item in old)
    result: list[CollectedItem] = []
    for item in new:
        if added.get(item.key, 0) > 0:
            added[item.key] -= 1
            continue
        result.append(item)
    return result


class MojeOdpadkyClient:
    """Klient držící přihlášenou session."""

    def __init__(
        self,
        login: str,
        password: str,
        slug: str | None = None,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self._login = login
        self._password = password
        self._slug = slug or None
        self._owns_session = session is None
        self._session = session or aiohttp.ClientSession(
            timeout=TIMEOUT,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "cs-CZ,cs;q=0.9"},
            cookie_jar=aiohttp.CookieJar(),
        )
        self._lock = asyncio.Lock()
        self._logged_in = False
        self._town: str | None = None

    @property
    def slug(self) -> str | None:
        """Adresní část obce, např. ``novalhota``."""
        return self._slug

    @property
    def town(self) -> str | None:
        """Název obce, např. ``Nová Lhota``. Známý až po ``async_fetch_town``."""
        return self._town

    async def async_close(self) -> None:
        """Zavřít vlastní session."""
        if self._owns_session and not self._session.closed:
            await self._session.close()

    @property
    def _calendar_url(self) -> str:
        if not self._slug:
            raise SlugNotFound("Není známa adresa obce")
        return f"{BASE}/{self._slug}/svozovy-kalendar"

    @property
    def _town_url(self) -> str:
        if not self._slug:
            raise SlugNotFound("Není známa adresa obce")
        return f"{BASE}/{self._slug}"

    @property
    def _nastenka_url(self) -> str:
        if not self._slug:
            raise SlugNotFound("Není známa adresa obce")
        return f"{BASE}/{self._slug}/nastenka"

    async def async_login(self) -> None:
        """Přihlásit se a zjistit adresu obce.

        Formulář je v hlavičce homepage (`action="/"`, skryté
        `_do=signInForm-submit`). Neúspěch i úspěch končí přesměrováním 303
        zpátky na `/`, server u neúspěchu nevrací žádnou chybovou hlášku -
        rozlišuje se proto podle toho, co je na výsledné stránce.
        """
        # Nejdřív obyčejný GET jako z prohlížeče, ať existuje session.
        try:
            await self._get(f"{BASE}/")
        except MojeOdpadkyError as err:
            _LOGGER.debug("Úvodní GET homepage selhal, zkouším rovnou POST: %s", err)

        payload = {
            "login": self._login,
            "password": self._password,
            "_submit": "Přihlásit",
            "_do": "signInForm-submit",
        }
        try:
            async with self._session.post(
                f"{BASE}/", data=payload, headers={"Referer": f"{BASE}/"}
            ) as resp:
                body = await resp.text()
                final_path = resp.url.path
                status = resp.status
        except aiohttp.ClientError as err:
            raise MojeOdpadkyError(f"Spojení selhalo: {err}") from err

        has_form = RE_SIGNIN.search(body) is not None
        has_signout = RE_SIGNOUT.search(body) is not None
        _LOGGER.debug(
            "Přihlášení: stav %s, cílová cesta %s, formulář %s, odhlášení %s, %s znaků",
            status,
            final_path,
            has_form,
            has_signout,
            len(body),
        )

        if has_form and not has_signout:
            # Server vrátil zase přihlašovací stránku.
            raise InvalidAuth("Server přihlášení odmítl")

        self._logged_in = True

        if not self._slug:
            self._slug = self._find_slug(final_path, body)

        if not self._slug:
            # Poslední pokus: přihlášená homepage načtená znovu.
            try:
                self._slug = self._find_slug("/", await self._get(f"{BASE}/"))
            except MojeOdpadkyError as err:
                _LOGGER.debug("Druhý pokus o zjištění obce selhal: %s", err)

        if not self._slug:
            raise SlugNotFound("Adresu obce se z přihlášeného webu nepodařilo zjistit")

        _LOGGER.debug("Adresa obce: %s", self._slug)

    @staticmethod
    def _find_slug(path: str, body: str) -> str | None:
        """Slug z cesty po přesměrování, jinak z odkazů na stránce."""
        match = RE_SLUG_PATH.match(path)
        if match:
            return match.group(1)

        link = RE_SLUG_LINK.search(body)
        if link:
            return link.group(1)
        return None

    async def async_fetch_page(self) -> str:
        """Stáhnout stránku svozového kalendáře, v případě potřeby se přihlásit."""
        async with self._lock:
            if not self._logged_in:
                await self.async_login()

            body = await self._get(self._calendar_url)

            if not self._is_calendar(body):
                # Session nejspíš vypršela - jeden pokus o obnovu.
                _LOGGER.debug("Kalendář nenalezen, obnovuji přihlášení")
                self._logged_in = False
                await self.async_login()
                body = await self._get(self._calendar_url)

            if not self._is_calendar(body):
                raise MojeOdpadkyError(
                    "Stránka svozového kalendáře nemá ani svozy, ani karty "
                    "harmonogramů - změnil se layout webu?"
                )

            if RE_EVENTS.search(body) is None:
                _LOGGER.debug(
                    "Kalendář je bez svozů - účet zatím nesleduje žádný harmonogram"
                )
            return body

    @staticmethod
    def _is_calendar(body: str) -> bool:
        """Je to přihlášená stránka svozového kalendáře?

        Nestačí hledat data-events: účet, který zatím nic nesleduje, kalendář
        se svozy nemá, a přitom ho přidat jde - harmonogramy se vybírají
        právě v průvodci. Proto stačí i karty harmonogramů bez přihlašovacího
        formuláře.
        """
        if RE_EVENTS.search(body):
            return True
        if RE_SIGNIN.search(body):
            return False
        return bool(RE_SUBSCRIBE.search(body) or RE_UNSUBSCRIBE.search(body))

    async def async_fetch_collected(self, page_size: int = 20) -> str:
        """Stáhnout první stránku nástěnky, tedy nejnovější odevzdání.

        Řadí se až v parseru, na parametr ``collectionsListSort`` se
        nespoléháme. Pro víc záznamů stačí zvýšit ``page_size``
        (server bere 5/10/20/50/100), na celou historii by se muselo stránkovat
        přes ``collectionsListPage``.
        """
        # Server bere jen tyhle velikosti; jiná se tiše ignoruje a vrátí 10.
        povolene = (5, 10, 20, 50, 100)
        if page_size not in povolene:
            page_size = min((x for x in povolene if x >= page_size), default=100)
        url = (
            f"{self._nastenka_url}"
            f"?collectionsListPageSize={page_size}&collectionsListPage=1"
        )
        async with self._lock:
            if not self._logged_in:
                await self.async_login()

            body = await self._get(url)

            if RE_SIGNIN.search(body):
                # Session vypršela - jeden pokus o obnovu.
                _LOGGER.debug("Nástěnka vrátila přihlašovací formulář, hlásím se znovu")
                self._logged_in = False
                await self.async_login()
                body = await self._get(url)

            return body

    async def async_fetch_town(self) -> str | None:
        """Zjistit název obce z titulku stránky ``/{slug}``.

        Stránka je veřejná, přihlášení není potřeba, a název obce se nemění -
        stahuje se proto jen jednou za běh. Když se ho nepodaří přečíst,
        vrací ``None`` a volající si vystačí se slugem.
        """
        if self._town:
            return self._town

        try:
            body = await self._get(self._town_url)
        except MojeOdpadkyError as err:
            _LOGGER.debug("Název obce se nepodařilo stáhnout: %s", err)
            return None

        self._town = self.parse_town(body)
        return self._town

    async def _get(self, url: str) -> str:
        try:
            async with self._session.get(url) as resp:
                resp.raise_for_status()
                return await resp.text()
        except aiohttp.ClientError as err:
            raise MojeOdpadkyError(f"GET {url} selhal: {err}") from err

    async def async_subscribe(
        self, schedule_id: int, notification: bool = False, email: str = ""
    ) -> None:
        """Začít sledovat harmonogram."""
        payload = {
            "_do": "subscribeForm-form-submit",
            "schedule_id": str(schedule_id),
            "notification": "1" if notification else "0",
            "email": email,
            "_submit": "Uložit",
        }
        try:
            async with self._session.post(
                self._calendar_url,
                data=payload,
                headers={"Referer": self._calendar_url},
            ) as resp:
                resp.raise_for_status()
                await resp.read()
        except aiohttp.ClientError as err:
            raise MojeOdpadkyError(
                f"Přihlášení harmonogramu {schedule_id} selhalo: {err}"
            ) from err

    async def async_set_notification(
        self, subscribe_id: int, email: str, schedule_id: int | None = None
    ) -> None:
        """Zapnout e-mailová upozornění u jednoho odběru.

        Odpovídá tlačítku „Zapnout upozornění" na kartě harmonogramu:
        modál posílá ID *odběru* (ne harmonogramu) a e-mail.
        """
        payload = {
            "subscribe_id": str(subscribe_id),
            "email": email,
            "_submit": "Uložit",
            "_do": "notificationForm-form-submit",
        }
        try:
            async with self._session.post(
                self._calendar_url,
                data=payload,
                headers={"Referer": self._calendar_url},
            ) as resp:
                resp.raise_for_status()
                await resp.read()
        except aiohttp.ClientError as err:
            raise MojeOdpadkyError(
                f"Zapnutí upozornění u odběru {subscribe_id} selhalo: {err}"
            ) from err

        if schedule_id is None:
            return

        # Server jednou zapnul upozornění u jiného harmonogramu, než jaké
        # ID odběru ze stránky říkalo. Od té doby se výsledek kontroluje.
        try:
            after = self.parse_schedules(await self.async_fetch_page())
        except MojeOdpadkyError as err:
            _LOGGER.debug("Kontrola zapnutí upozornění neproběhla: %s", err)
            return

        zapnute = [item.schedule_id for item in after if item.notifications]
        if schedule_id not in zapnute:
            raise MojeOdpadkyError(
                f"Server upozornění u harmonogramu {schedule_id} nezapnul "
                f"(zapnutá jsou u {zapnute or 'žádného'}). "
                "Zkontrolujte to prosím na webu."
            )

    async def async_unset_notification(self, subscribe_id: int) -> None:
        """Vypnout e-mailová upozornění u odběru.

        Odpovídá odkazu „Vypnout upozornění" na kartě harmonogramu, který se
        objeví, až když jsou upozornění zapnutá.
        """
        url = f"{self._calendar_url}?subscribeId={subscribe_id}&do=NotificationOff"
        await self._get(url)

    async def async_unsubscribe(self, schedule_id: int) -> None:
        """Přestat sledovat harmonogram."""
        url = f"{self._calendar_url}?scheduleId={schedule_id}&do=Unsubscribe"
        await self._get(url)

    @staticmethod
    def parse_events(body: str) -> list[CollectionEvent]:
        """Vytáhnout svozy z atributu data-events."""
        match = RE_EVENTS.search(body)
        if not match:
            return []
        try:
            raw = json.loads(html_lib.unescape(match.group(1)))
        except json.JSONDecodeError as err:
            raise MojeOdpadkyError(f"data-events není platný JSON: {err}") from err

        events: list[CollectionEvent] = []
        for item in raw:
            try:
                day = date.fromisoformat(item["start"])
            except (KeyError, ValueError):
                continue
            events.append(
                CollectionEvent(
                    day=day,
                    waste_type=item.get("title", "").strip(),
                    schedule_name=" ".join(item.get("description", "").split()),
                )
            )
        # Pole ze serveru je seřazené po harmonogramech, ne podle data,
        # a u bioodpadu jsou svozy navíc přilepené na konci.
        events.sort(key=lambda e: (e.day, e.waste_type))
        return events

    @staticmethod
    def parse_schedules(body: str) -> list[Schedule]:
        """Vytáhnout všechny harmonogramy - sledované i nesledované."""
        schedules: list[Schedule] = []
        seen: set[int] = set()

        for chunk in RE_CARD_SPLIT.split(body):
            unsub = RE_UNSUBSCRIBE.search(chunk)
            sub = RE_SUBSCRIBE.search(chunk)
            if not unsub and not sub:
                continue

            title = RE_TITLE.search(chunk)
            if not title:
                continue

            schedule_id = int(unsub.group(1) if unsub else sub.group(1))
            if schedule_id in seen:
                continue
            seen.add(schedule_id)

            notify = RE_NOTIFY_ID.search(chunk)
            notify_off = RE_NOTIFY_OFF.search(chunk)
            notify_state = RE_NOTIFY_STATE.search(chunk)
            span = RE_RANGE.search(chunk)

            schedules.append(
                Schedule(
                    schedule_id=schedule_id,
                    name=_strip_tags(title.group(1)),
                    subscribed=unsub is not None,
                    subscribe_id=int(
                        notify.group(1) if notify else notify_off.group(1)
                    )
                    if (notify or notify_off)
                    else None,
                    # Odkaz na vypnutí je jistota; text karty je záložní.
                    notifications=bool(notify_off)
                    or bool(
                        not notify
                        and notify_state
                        and "vypnut" not in _strip_tags(notify_state.group(1)).lower()
                    ),
                    date_from=_parse_cz_date(span.group(1)) if span else None,
                    date_to=_parse_cz_date(span.group(2)) if span else None,
                )
            )

        return schedules

    @staticmethod
    def parse_default_email(body: str) -> str:
        """Předvyplněný e-mail z formuláře odběru."""
        start = body.find('id="frm-subscribeForm-form"')
        match = RE_EMAIL.search(body if start == -1 else body[start:])
        return html_lib.unescape(match.group(1)) if match else ""

    @staticmethod
    def parse_town(body: str) -> str | None:
        """Název obce z ``<title>`` stránky obce.

        "Aktuality Nová Lhota | Moje odpadky" -> "Nová Lhota".
        """
        match = RE_PAGE_TITLE.search(body)
        if not match:
            return None

        title = " ".join(html_lib.unescape(match.group(1)).split())
        name = title.split("|")[0].strip()

        for label in TITLE_PAGE_LABELS:
            if name.lower().startswith(label.lower()):
                name = name[len(label):].strip()
                break

        if not name or name.lower().startswith("chyba"):
            # Chybová stránka nebo titulek bez názvu obce.
            return None
        return name

    @staticmethod
    def parse_collected(body: str) -> list[CollectedItem]:
        """Vytáhnout záznamy svezeného odpadu z nástěnky.

        Tabulka se hledá podle hlavičky (komodita + nádoba / EKO body), protože
        pořadí tabulek na stránce není jisté. Když hlavička nesedí, projdou se
        všechny řádky stránky a berou se ty, které začínají datem.
        """
        rows: list[str] = []
        for table in RE_TABLE.findall(body):
            table_rows = RE_ROW.findall(table)
            if not table_rows:
                continue
            header = _cell_text(table_rows[0]).lower()
            # Na nástěnce jsou tabulky, které matou: "Moje nádoby" má
            # "Označení nádoby" i "Komodita", "Podrobnosti svozů" zase
            # "Komodita" a "Počet osob používajícíh nádobu". Ta naše je
            # jediná, která má zároveň Datum, Komoditu a Označení nádoby
            # (nebo EKO body). Bere se první, která sedí.
            if (
                "datum" in header
                and "komodita" in header
                and ("označení nádob" in header or "eko bod" in header)
            ):
                rows = table_rows
                break

        if not rows:
            # Nouzový režim: hlavička nesedí, berou se řádky z celé stránky.
            # Může nachytat i cizí tabulky, proto ať je to vidět v logu.
            _LOGGER.warning(
                "Tabulku svezeného odpadu se nepodařilo najít podle hlavičky, "
                "čtou se všechny řádky stránky - změnil se layout webu?"
            )
            rows = RE_ROW.findall(body)

        items: list[CollectedItem] = []
        for row in rows:
            cells = [_cell_text(cell) for cell in RE_CELL.findall(row)]
            if len(cells) < 3 or not RE_CZ_DATE.match(cells[0]):
                # Hlavička i patička tabulky; datum v prvním sloupci je
                # jediný spolehlivý znak datového řádku.
                continue
            day = _parse_cz_date(cells[0].replace(" ", ""))
            if day is None:
                continue
            items.append(
                CollectedItem(
                    day=day,
                    waste_type=cells[1],
                    container=cells[2],
                    points=cells[3] if len(cells) > 3 else "",
                )
            )

        # Nejnovější první. Řadí se jen podle data - řazení je stabilní,
        # takže pořadí záznamů z jednoho dne zůstane takové, jak je posílá
        # server (na nástěnce jsou v tom pořadí i vidět).
        items.sort(key=lambda item: item.day, reverse=True)
        return items

    @property
    def _inventory_url(self) -> str:
        if not self._slug:
            raise SlugNotFound("Není známa adresa obce")
        return f"{BASE}/{self._slug}/inventura-stanoviste"

    async def async_fetch_inventory(self) -> str:
        """Stáhnout stránku Inventura stanoviště."""
        async with self._lock:
            if not self._logged_in:
                await self.async_login()

            body = await self._get(self._inventory_url)

            if RE_SIGNIN.search(body):
                self._logged_in = False
                await self.async_login()
                body = await self._get(self._inventory_url)

            return body

    @staticmethod
    def parse_people(body: str, text: str | None = None) -> int | None:
        """Aktuální počet osob na stanovišti z inventury."""
        match = RE_PEOPLE_NOW.search(text if text is not None else page_text(body))
        return int(match.group(1)) if match else None

    @property
    def _rating_url(self) -> str:
        if not self._slug:
            raise SlugNotFound("Není známa adresa obce")
        return f"{BASE}/{self._slug}/hodnoceni-stanoviste"

    async def async_fetch_rating(self) -> str:
        """Stáhnout stránku Hodnocení stanoviště.

        Je velká (kolem 0,7 MB), proto se čte jen to podstatné a nikde
        se neukládá.
        """
        async with self._lock:
            if not self._logged_in:
                await self.async_login()

            body = await self._get(self._rating_url)

            if RE_SIGNIN.search(body):
                self._logged_in = False
                await self.async_login()
                body = await self._get(self._rating_url)

            return body

    @staticmethod
    def parse_rating(body: str, text: str | None = None) -> Rating | None:
        """Objem na osobu, počet osob a období z Hodnocení stanoviště."""
        text = text if text is not None else page_text(body)

        volume = RE_VOLUME.search(text)
        if not volume:
            return None

        def cislo(value: str | None) -> float | None:
            if not value:
                return None
            cisty = value.replace(" ", "").replace(",", ".")
            try:
                return float(cisty)
            except ValueError:
                return None

        celkem = cislo(volume.group(1))
        if celkem is None:
            return None

        people = None
        lide = RE_PEOPLE.search(text)
        if lide:
            # Řádek je po měsících, platí poslední hodnota.
            people = int(lide.group(1).split()[-1])

        obdobi = RE_PERIOD.search(text)

        return Rating(
            volume_person=celkem,
            mixed_person=cislo(volume.group(2)),
            sorted_person=cislo(volume.group(3)),
            people=people,
            period_from=_parse_cz_date(obdobi.group(1)) if obdobi else None,
            period_to=_parse_cz_date(obdobi.group(2)) if obdobi else None,
        )

    @staticmethod
    def parse_score(body: str, text: str | None = None) -> Score | None:
        """Skóre MESOH z nástěnky: získané body, maximum a využití v procentech."""
        text = text if text is not None else page_text(body)
        body_match = RE_SCORE.search(text)
        if not body_match:
            return None

        def cislo(value: str) -> float:
            return float(value.replace(",", "."))

        points = cislo(body_match.group(1))
        max_points = cislo(body_match.group(2))

        percent_match = RE_SCORE_PERCENT.search(text)
        if percent_match:
            percent = cislo(percent_match.group(1))
        else:
            percent = round(points / max_points * 100, 1) if max_points else 0.0

        return Score(points=points, max_points=max_points, percent=percent)

    @staticmethod
    def parse_fee(body: str, text: str | None = None) -> Fee | None:
        """Blok „Poplatek za odpady na rok ..." z nástěnky.

        Je to volný text s nedělitelnými mezerami, žádná tabulka - čte se
        proto ze stránky bez značek.
        """
        text = text if text is not None else page_text(body)

        year = RE_FEE_YEAR.search(text)
        rate = RE_FEE_RATE.search(text)
        total = RE_FEE_TOTAL.search(text)
        discount = RE_FEE_DISCOUNT.search(text)
        if not (year and rate and total):
            return None

        def cislo(value: str) -> int:
            return int(re.sub(r"\D", "", value))

        return Fee(
            year=int(year.group(1)),
            rate=cislo(rate.group(1)),
            discount=cislo(discount.group(1)) if discount else 0,
            discount_percent=float(discount.group(2).replace(",", "."))
            if discount
            else 0.0,
            total=cislo(total.group(1)),
        )

    @staticmethod
    def parse_collected_total(body: str, text: str | None = None) -> int | None:
        """Celkový počet záznamů z textu „Zobrazeno 10 ze 747 záznamů"."""
        match = RE_TOTAL.search(text if text is not None else page_text(body))
        if not match:
            return None
        digits = re.sub(r"\D", "", match.group(1))
        return int(digits) if digits else None

    async def async_apply_selection(
        self, wanted: set[int], unsubscribe: bool = False, body: str | None = None
    ) -> str:
        """Dorovnat odběry na serveru podle výběru a vrátit čerstvou stránku.

        Odhlašuje se **jen na výslovné přání** (``unsubscribe=True``).
        Automatické odhlašování na pozadí už jednou sebralo uživateli odběr,
        který chtěl - výběr v Home Assistantu umí být rozejitý s webem
        z mnoha důvodů (ruční změna na webu, přelom roku, nová ID), a smazat
        kvůli tomu odběr je nevratné.
        """
        if body is None:
            body = await self.async_fetch_page()
        email = self.parse_default_email(body)
        current = {s.schedule_id for s in self.parse_schedules(body) if s.subscribed}

        to_add = wanted - current
        to_remove = current - wanted

        if not wanted and current:
            # Prazdny vyber je skoro jiste chyba konfigurace, ne pokyn
            # odhlasit uzivateli vsechno. Radeji nesaheme na nic.
            _LOGGER.warning(
                "Výběr harmonogramů je prázdný, odběry na webu nechávám beze změny"
            )
            return body

        for schedule_id in sorted(to_add):
            _LOGGER.info("Začínám sledovat harmonogram %s", schedule_id)
            await self.async_subscribe(schedule_id, False, email)

        if to_remove and not unsubscribe:
            _LOGGER.info(
                "Na webu jsou navíc sledované harmonogramy %s; integrace je "
                "nechává být, odhlásit je jde na webu mojeodpadky.cz",
                sorted(to_remove),
            )
        elif to_remove:
            for schedule_id in sorted(to_remove):
                _LOGGER.info("Přestávám sledovat harmonogram %s", schedule_id)
                await self.async_unsubscribe(schedule_id)

        if not to_add and not (to_remove and unsubscribe):
            return body

        return await self.async_fetch_page()
