<p align="center">
  <img src="docs/logo.png" alt="Moje odpadky" width="112">
</p>

<p align="center"><strong>Moje odpadky pro Home Assistant</strong></p>

<p align="center">
  Svozový kalendář, senzory příštích svozů a historie odevzdaného odpadu<br>
  z <a href="https://www.mojeodpadky.cz">mojeodpadky.cz</a> přímo v Home Assistantu.
</p>

<p align="center">
  <img alt="Verze" src="https://img.shields.io/github/v/release/joazif/ha-mojeodpadky?style=flat-square&color=4c8b2b&label=verze">
  <img alt="Stažení" src="https://img.shields.io/github/downloads/joazif/ha-mojeodpadky/total?style=flat-square&color=4c8b2b&label=sta%C5%BEen%C3%AD">
  <img alt="HACS" src="https://img.shields.io/badge/HACS-vlastn%C3%AD%20repozit%C3%A1%C5%99-4c8b2b?style=flat-square">
  <img alt="Home Assistant" src="https://img.shields.io/badge/Home%20Assistant-2024.6%2B-4c8b2b?style=flat-square">
  <img alt="Vibe coded" src="https://img.shields.io/badge/vibe-coded-4c8b2b?style=flat-square">
</p>

> [!WARNING]
> **Neoficiální integrace.** Nevytvořil ji provozovatel mojeodpadky.cz, není jím
> vyvíjená ani podporovaná. Přihlašuješ se vlastními údaji na vlastní
> odpovědnost — autor nenese odpovědnost za to, co se s tvým účtem stane,
> ani za škody vzniklé používáním integrace. Logo patří provozovateli
> mojeodpadky.cz.

> [!NOTE]
> Kód je **vibe coding** — nepsal ho člověk řádek po řádku, ale jazykový model
> podle popisu toho, co má integrace umět.

## Co to umí

- **Svozy:** kalendářová entita se všemi svozy roku a senzor pro každou
  komoditu se stavem **Dnes / Zítra / Za 5 dní**.
- **Harmonogramy:** přihlášení jménem a heslem, obec se zjistí sama. Seznam
  všech harmonogramů obce jako zaškrtávátka — zaškrtnutí harmonogram na webu
  přihlásí, odškrtnutí odhlásí.
- **Odevzdaný odpad:** posledních 15 záznamů z nástěnky, počet odevzdání
  každé komodity za MESOH rok i se součtem a událost pro automatizace při
  každém novém záznamu.
- **MESOH:** skóre (EKO body a využití systému), obsloužený objem na osobu,
  počet osob na stanovišti, konec MESOH roku a odpočet dní do něj.
- **Poplatek:** předpokládaný poplatek na příští rok, sazba, úleva v korunách
  i procentech — každé zvlášť, aby šel dělat graf.
- **E-mailová upozornění** z webu se zapínají a vypínají pro každý harmonogram
  zvlášť, stejně jako na webu.
- **Víc účtů a víc obcí** — každé přihlášení je samostatná služba.
- Tlačítko **Aktualizovat**, interval stahování 1 / 3 / 6 / 24 hodin.

## Instalace

### HACS (doporučeno)

[![Otevřít repozitář v HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=joazif&repository=ha-mojeodpadky&category=integration)

Nebo ručně:

1. HACS → ⋮ → **Custom repositories**
2. Repozitář `https://github.com/joazif/ha-mojeodpadky`, kategorie **Integration**
3. Najdi *Moje odpadky*, klikni **Download**
4. Restartuj Home Assistant
5. **Nastavení → Zařízení a služby → Přidat integraci → Moje odpadky**

[![Přidat integraci](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=mojeodpadky)

### Ručně

Zkopíruj `custom_components/mojeodpadky/` do své konfigurační složky
(`/config/custom_components/mojeodpadky/`), restartuj Home Assistant
a přidej integraci v UI.

## Víc účtů a víc obcí

Každé přihlášení je samostatná služba. Další účet přidáš v **Nastavení →
Zařízení a služby → Moje odpadky → Přidat službu** — třeba člena rodiny ve
stejné obci, nebo účet v úplně jiné obci. Každý má vlastní zařízení, vlastní
entity a vlastní výběr harmonogramů.

Jak se zařízení pojmenují:

| Účet | Název zařízení | Entity |
|---|---|---|
| první účet v obci | `Nová Lhota` | `sensor.nova_lhota_papir` |
| další účet v téže obci | `Nová Lhota (jiny_login)` | `sensor.nova_lhota_jiny_login_papir` |
| účet v jiné obci | `Horní Ves` | `sensor.horni_ves_papir` |

Stejný login podruhé přidat nejde.

## Obec

Nikde se nezadává. Integrace ji zjistí z přihlášeného webu — z adresy po
přesměrování nebo z odkazu na svozový kalendář. Název pak přečte z titulku
veřejné stránky obce a použije ho jako název zařízení, takže entity vznikají
jako `sensor.<tvoje_obec>_papir`. Druhý krok průvodce obec rovnou ukáže,
ať je vidět, že se trefila.

## Entity

Rozdělené tak, jak je ukazuje stránka zařízení.

### Senzory

| Entita | Stav | Zajímavé atributy |
|---|---|---|
| Kalendář (jmenuje se podle obce) | `Zapnuto` v den svozu | všechny svozy roku |
| `sensor.<obec>_<komodita>` | `Za 15 dní` | `datum`, `days_to`, `harmonogram` |
| `sensor.<obec>_pristi_svoz` | `Zítra` | `datum`, `days_to`, `types` |
| `sensor.<obec>_posledni_odevzdani` | `Včera` | `datum`, `komodita`, `nadoba`, `zaznamy` |
| `sensor.<obec>_predpokladany_poplatek` | `900 Kč` | `rok`, `sazba`, `uleva`, `uleva_procent` |
| `sensor.<obec>_sazba_poplatku` | `1200 Kč` | `rok` |
| `sensor.<obec>_uleva_mesoh` | `300 Kč` | `rok` |
| `sensor.<obec>_uleva_v_procentech` | `25 %` | `rok` |
| `sensor.<obec>_eko_body` | `33,5 bodů` | `maximum`, `vyuziti_procent` |
| `sensor.<obec>_vyuziti_systemu` | `30,3 %` | `body`, `maximum` |
| `sensor.<obec>_objem_na_osobu` | `5753 l` | `smesny_l`, `tridene_l`, `obdobi_od`, `obdobi_do` |
| `sensor.<obec>_osob_na_stanovisti` | `4 osob` | — |
| `sensor.<obec>_konec_mesoh_roku` | datum konce | `zacatek`, `zbyva_dni` |
| `sensor.<obec>_do_konce_mesoh_roku` | `6 dní` | `konec`, `konec_text` |

Stav senzorů komodit je jen na čtení a mění se každý den. Automatizace se
proto váže na atributy (`days_to`, `datum`), ne na text.

Sazba, úleva a procenta jsou atributy poplatku **i samostatné senzory** —
atributy se do dlouhodobých statistik neukládají, graf by z nich nebyl.

*Konec MESOH roku* je typu datum, takže tvar určuje tvůj profil
(**Profil → Obecné → Formát data**).

### Ovládací prvky

| Entita | Co dělá |
|---|---|
| `button.<obec>_aktualizovat` | stáhne data hned, bez čekání na interval |
| `switch.<obec>_upozorneni_<komodita>` | e-mailová upozornění z webu pro jeden harmonogram |

Přepínač se jmenuje podle komodity („Upozornění: Papír"). Když má obec víc
harmonogramů téže komodity, přidá se to, čím se liší: místní část psaná velkými
písmeny („Bioodpad Záhoří"), první slovo, které ten druhý nemá (typicky
letopočet), a v krajním případě ID harmonogramu. Celý název je v atributu
`harmonogram`.

### Diagnostika

| Entita | Stav | Zajímavé atributy |
|---|---|---|
| `26 – Plast`, `26 – Papír`… | `51 ×` | `eko_body`, `posledni_odevzdani`, `nadoba`, `obdobi_od`, `obdobi_do` |
| `26 – Σ Celkem` | `167 ×` | rozpis podle komodit |
| Poslední úspěšná aktualizace | `20.09.2026 23:18` | `cas`, `posledni_pokus_uspesny` |

Číslo na začátku počtů je rok, kdy MESOH rok končí (2025/26 → 26). Díky němu
drží počty v abecedním řazení pohromadě a `Σ` se řadí za všechna písmena,
takže je součet vždycky dole. 1. října se počty vynulují a název se přepne
na další rok.

Atribut `eko_body` říká, kolik bodů dalo poslední odevzdání té komodity
(plast 3,4, papír 3…). Při každém stažení se hledá nejnovější záznam na
nástěnce i v tabulce za celý MESOH rok, takže když obec bodování změní,
uvidíš to po kliknutí na počet.

## Karta: přehled svozů

> [!IMPORTANT]
> `<obec>` v příkladech nahraď svou obcí — přesné názvy entit najdeš
> ve Vývojářských nástrojích → Stavy (filtr `odevzdani`, resp. `poplatek`).

Komodity, souhrny a poplatek v jedné kartě:

```yaml
type: entities
title: Svoz odpadu
entities:
  - entity: sensor.<obec>_bio
    name: Bio
  - entity: sensor.<obec>_papir
    name: Papír
  - entity: sensor.<obec>_plast
    name: Plast
  - entity: sensor.<obec>_smesny_odpad
    name: Směsný odpad
  - type: divider
  - entity: sensor.<obec>_posledni_odevzdani
    name: Poslední odevzdání
  - entity: sensor.<obec>_pristi_svoz
    name: Příští svoz
  - type: divider
  - entity: sensor.<obec>_predpokladany_poplatek
    name: Po úlevě
    icon: mdi:cash
  - entity: sensor.<obec>_sazba_poplatku
    name: Sazba
  - entity: sensor.<obec>_uleva_mesoh
    name: Úleva MESOH
  - entity: sensor.<obec>_uleva_v_procentech
    name: Úleva
```

Komodity se jmenují podle toho, co posílá web, takže `bio`, `papir`, `plast`
a `smesny_odpad` u jiné obce můžou vypadat jinak. Tlačítko ruční aktualizace
se přidá jako `- entity: button.<obec>_aktualizovat`.

## Karta: co jsem odevzdal

Dlaždice s ikonou a barvou podle komodity. Potřebuje z HACS dvě karty:
[Mushroom](https://github.com/piitaya/lovelace-mushroom)
a [auto-entities](https://github.com/thomasloven/lovelace-auto-entities).

```yaml
type: vertical-stack
cards:
  - type: heading
    heading: Co jsem odevzdal
  - type: custom:auto-entities
    show_empty: false
    card:
      type: grid
      columns: 2
      square: false
    card_param: cards
    filter:
      template: |-
        {%- set e = 'sensor.<obec>_posledni_odevzdani' -%}
        {%- set zaznamy = state_attr(e, 'zaznamy') or [] -%}
        {%- set vzhled = {
          'Směsný odpad': ['mdi:trash-can', 'grey'],
          'Plast': ['mdi:recycle', 'yellow'],
          'Papír': ['mdi:newspaper-variant-multiple', 'blue'],
          'Bio': ['mdi:leaf', 'brown'],
          'Sklo': ['mdi:bottle-wine', 'green'],
          'Kov': ['mdi:silverware-fork-knife', 'blue-grey'],
          'Kovy': ['mdi:silverware-fork-knife', 'blue-grey'],
          'Elektro': ['mdi:television-classic', 'red'],
          'NO': ['mdi:biohazard', 'red'],
          'Dřevo': ['mdi:pine-tree', 'brown'],
          'Pneumatiky': ['mdi:tire', 'grey'],
          'Suť': ['mdi:wall', 'grey'],
          'Textil': ['mdi:tshirt-crew', 'purple'],
          'Jedlý olej a tuk': ['mdi:oil', 'orange']
        } -%}
        {%- set ns = namespace(cards=[]) -%}
        {%- for z in (zaznamy | sort(attribute='datum', reverse=true))[:10] -%}
          {%- set v = vzhled.get(z.komodita, ['mdi:trash-can-outline', 'disabled']) -%}
          {%- set ns.cards = ns.cards + [{
            'type': 'custom:mushroom-template-card',
            'entity': e,
            'primary': z.komodita,
            'secondary': as_datetime(z.datum).strftime('%-d. %-m. %Y') ~ ' · ' ~ z.nadoba,
            'icon': v[0],
            'color': v[1],
            'tap_action': {'action': 'none'}
          }] -%}
        {%- endfor -%}
        {{ ns.cards }}
```

Každý záznam má klíče `datum` (ISO, `2026-09-19`), `komodita`, `nadoba`
a `ekobody`. `NO` je nebezpečný odpad. Komodity, které v mapě `vzhled`
nejsou, dostanou šedou popelnici, takže kartu nerozbijí.

## Automatizace

Připomenutí den předem:

```yaml
automation:
  - alias: Připomenout popelnice
    triggers:
      - trigger: time
        at: "18:00:00"
    conditions:
      - condition: template
        value_template: >-
          {{ state_attr('sensor.<obec>_smesny_odpad', 'days_to') == 1 }}
    actions:
      - action: notify.mobile_app
        data:
          message: Zítra se sváží směsný odpad.
```

Upozornění na nový záznam v nástěnce. Událost se vyvolá pro každé odevzdání,
které přibylo od minulého obnovení; při prvním stažení mlčí:

```yaml
automation:
  - alias: Zapsáno na nástěnce
    triggers:
      - trigger: event
        event_type: mojeodpadky_odevzdano
    actions:
      - action: notify.mobile_app
        data:
          message: >-
            {{ trigger.event.data.ucet }}: {{ trigger.event.data.komodita }}
            ({{ trigger.event.data.nadoba }}), {{ trigger.event.data.datum }}.
```

Při víc účtech nese událost pole `ucet` (název služby) a `entry_id`, takže jde
automatizaci omezit jen na jeden účet:

```yaml
    triggers:
      - trigger: event
        event_type: mojeodpadky_odevzdano
        event_data:
          ucet: Nová Lhota (jiny_login)
```

### Připomenutí konce MESOH roku

MESOH rok běží od 1. 10. do 30. 9. a body se počítají jen za ten rok.
Senzor *Do konce MESOH roku* je číslo, takže na něj jde postavit podmínka:

```yaml
automation:
  - alias: Blíží se konec MESOH roku
    triggers:
      - trigger: numeric_state
        entity_id: sensor.<obec>_do_konce_mesoh_roku
        below: 15
    actions:
      - action: notify.mobile_app
        data:
          message: >-
            MESOH rok končí
            {{ state_attr('sensor.<obec>_do_konce_mesoh_roku', 'konec_text') }},
            zbývá {{ states('sensor.<obec>_do_konce_mesoh_roku') }} dní.
```

`numeric_state` se spustí jednou, ve chvíli kdy hodnota klesne pod hranici —
ne každý den znovu.

## Poznámky

- **Odhlašuje se jen při změně výběru v Home Assistantu.** Integrace si
  pamatuje, co naposledy na web promítla. Změnu udělanou na webu respektuje
  a nepřepisuje ji, prázdný výběr ignoruje — aby rozejitý stav nebo chyba
  v nastavení neodhlásila odběr, o který nikdo nepřišel dobrovolně.
- **Přelom roku:** obec vypíše nové harmonogramy s novými ID a staré zmizí.
  Integrace si u vybraných harmonogramů pamatuje komoditu a místní část,
  takže výběr sama převede na letošní obdobu. Když nástupce nenajde, napíše
  to do logu.
- Po zapnutí e-mailových upozornění se výsledek ověřuje; když server zapne
  upozornění jinde, přepínač to ohlásí jako chybu.
- Senzory, jejichž stav závisí na dnešku, se přepočítají po půlnoci samy.
- Když nástěnka nebo hodnocení selže, senzory svozů jedou dál.

## Jak to funguje uvnitř

Stránka svozového kalendáře nese celý rok v atributu `data-events` elementu
`#collectionScheduleCalendar` (JSON pro FullCalendar), takže na stažení stačí
jediný GET s přihlášenou session. Nástěnka a hodnocení stanoviště jsou
obyčejné HTML tabulky. Žádné API, žádné XHR.

Přihlášení i přepínání odběrů jsou obyčejné požadavky bez CSRF tokenu:

| Akce | Metoda | Payload |
|---|---|---|
| Přihlášení | POST na `/` | `login`, `password`, `_do=signInForm-submit`, `_submit=Přihlásit` |
| Začít sledovat | POST | `_do=subscribeForm-form-submit`, `schedule_id`, `notification`, `email` |
| Přestat sledovat | GET | `?scheduleId=<id>&do=Unsubscribe` |
| Zapnout upozornění | POST | `_do=notificationForm-form-submit`, `subscribe_id`, `email` |
| Vypnout upozornění | GET | `?subscribeId=<id>&do=NotificationOff` |

Bez externích závislostí, parsuje se regexy ze standardní knihovny.

## Testy

```bash
python3 tests/test_parsers.py
```

Testuje parsery proti markupu ze skutečné stránky (osobní údaje jsou ve
fixture nahrazené neutrálními hodnotami a obec smyšlenou). Před zveřejněním
změn se hodí pustit i `./tools/kontrola-udaju.sh`.

## Přístup k datům

Data poskytuje [mojeodpadky.cz](https://www.mojeodpadky.cz). Integrace je
neoficiální a s provozovatelem služby nemá žádný vztah.

Integrace se přihlašuje uživatelskými údaji a čte běžné stránky webu.
Nepoužívá žádné neveřejné rozhraní.

Data se obnovují podle nastaveného intervalu, standardně každých šest hodin.
Jedno obnovení stáhne svozový kalendář a první stránku nástěnky. Hodnocení
stanoviště a inventura se berou jen tehdy, když na nástěnce přibude nový
záznam, nebo nejvýš jednou za den — hodnocení má skoro megabajt a mění se
právě jen po svozu.

Logo v záhlaví patří provozovateli mojeodpadky.cz.

Pokud si provozovatel nepřeje, aby integrace existovala, otevřete prosím
[issue](https://github.com/joazif/ha-mojeodpadky/issues) — repozitář bude
stažen.
