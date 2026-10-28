<p align="center">
  <img src="https://raw.githubusercontent.com/joazif/ha-mojeodpadky/main/docs/logo.png" alt="Moje odpadky" width="112">
</p>

<p align="center"><strong>Moje odpadky pro Home Assistant</strong></p>

<p align="center">
  Svozový kalendář, senzory příštích svozů a historie odevzdaného odpadu<br>
  z <a href="https://www.mojeodpadky.cz">mojeodpadky.cz</a> přímo v Home Assistantu.
</p>

<p align="center">
  <img alt="Verze" src="https://img.shields.io/github/v/release/joazif/ha-mojeodpadky?style=flat-square&color=4c8b2b&label=verze">
  <img alt="Stažení" src="https://img.shields.io/github/downloads/joazif/ha-mojeodpadky/total?style=flat-square&color=4c8b2b&label=sta%C5%BEen%C3%AD">
  <img alt="HACS" src="https://img.shields.io/badge/HACS-integrace-4c8b2b?style=flat-square">
  <img alt="Home Assistant" src="https://img.shields.io/badge/Home%20Assistant-2024.11%2B-4c8b2b?style=flat-square">
</p>

> [!WARNING]
> **Neoficiální integrace.** Nevytvořil ji provozovatel mojeodpadky.cz, není jím
> vyvíjená ani podporovaná. Přihlašuješ se vlastními údaji na vlastní
> odpovědnost — autor nenese odpovědnost za to, co se s tvým účtem stane,
> ani za škody vzniklé používáním integrace. Logo patří provozovateli
> mojeodpadky.cz.

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
- **E-mailová upozornění** z webu se zapínají a vypínají pro každou sledovanou
  komoditu zvlášť.
- **Víc účtů a víc obcí** — každé přihlášení je samostatná služba.
- Tlačítko **Aktualizovat**, interval stahování 1 / 3 / 6 / 24 hodin.

## Instalace

### HACS (doporučeno)

1. Otevři HACS, vyhledej **Moje odpadky** a klikni **Download**
2. Restartuj Home Assistant
3. **Nastavení → Zařízení a služby → Přidat integraci → Moje odpadky**

[![Otevřít v HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=joazif&repository=ha-mojeodpadky&category=integration)
[![Přidat integraci](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=mojeodpadky)

Když ji HACS ve vyhledávání nenajde, přidej ji jako vlastní repozitář:

1. HACS → ⋮ → **Custom repositories**
2. Repozitář `https://github.com/joazif/ha-mojeodpadky`, kategorie **Integration**
3. Pak pokračuj krokem 1 výše

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
| Kalendář (jmenuje se podle obce) | `Zapnuto` v den svozu | nejbližší svoz; všechny svozy roku jsou jeho události |
| `sensor.<obec>_<komodita>` | `Za 15 dní` | `datum`, `days_to`, `harmonogram` |
| `sensor.<obec>_pristi_svoz` | `Zítra` | `datum`, `days_to`, `types` |
| `sensor.<obec>_posledni_odevzdani` | `Včera` | `datum`, `komodita`, `nadoba`, `zaznamy` |
| `sensor.<obec>_predpokladany_poplatek` | `900 Kč` | `rok`, `sazba`, `uleva`, `uleva_procent` |
| `sensor.<obec>_sazba_poplatku` | `1200 Kč` | `rok` |
| `sensor.<obec>_uleva_mesoh` | `300 Kč` | `rok` |
| `sensor.<obec>_uleva_v_procentech` | `25 %` | `rok` |
| `sensor.<obec>_eko_body` | `33,5 bodů` | `maximum`, `vyuziti_procent`, `obdobi_od`, `obdobi_do` |
| `sensor.<obec>_vyuziti_systemu` | `30,3 %` | `body`, `maximum` |
| `sensor.<obec>_objem_na_osobu` | `5753 l` | `smesny_l`, `tridene_l`, `obdobi_od`, `obdobi_do` |
| `sensor.<obec>_osob_na_stanovisti` | `4 osob` | — |
| `sensor.<obec>_konec_mesoh_roku` | datum konce | `zacatek`, `zbyva_dni` |
| `sensor.<obec>_do_konce_mesoh_roku` | `6 dní` | `konec`, `konec_text` |

Stav senzorů komodit je jen na čtení a mění se každý den. Automatizace se
proto váže na atributy (`days_to`, `datum`), ne na text.

Senzor komodity existuje, jen dokud má nějaký další svoz. Když obec komoditu
přestane svážet (třeba papír a plast zvlášť nahradí společný svoz „Papír,
Plast“), senzor zmizí, místo aby navždy ukazoval „Neznámý“. Jakmile se svozy
komodity znovu objeví, vrátí se se stejným ID.

Sazba, úleva a procenta jsou atributy poplatku **i samostatné senzory** —
atributy se do dlouhodobých statistik neukládají, graf by z nich nebyl.

*Konec MESOH roku* je typu datum, takže tvar určuje tvůj profil
(**Profil → Obecné → Formát data**).

### Ovládací prvky

| Entita | Co dělá |
|---|---|
| `button.<obec>_aktualizovat` | stáhne data hned, bez čekání na interval |
| `switch.<obec>_upozorneni_<komodita>` | e-mailová upozornění z webu pro jednu komoditu |

Přepínač se jmenuje podle komodity tak, jak ji web uvádí u svozů
(„Upozornění: Papír“, „Upozornění: Papír, Plast“). Komodita se nebere z názvu
harmonogramu: ten si obec píše každý rok jinak (třeba celý velkými písmeny),
svozy v kalendáři ji ale nesou vždycky stejně. Letopočet v názvu ani v ID
není a víc sledovaných harmonogramů téže komodity (starý a nový ročník, dva
harmonogramy bioodpadu) ovládá jeden přepínač. Když komoditu už žádný
sledovaný harmonogram nemá, přepínač zmizí. Celé názvy harmonogramů jsou
v atributu `harmonogram`.

### Diagnostika

| Entita | Stav | Zajímavé atributy |
|---|---|---|
| `2026/27` (MESOH rok) | `01.10.2026 – 30.09.2027` | `od`, `do`, `rok` |
| Aktualizováno | `20.09.2026 23:18` | `cas`, `posledni_pokus_uspesny` |
| `Plast`, `Papír`… | `51 ×` | `eko_body`, `posledni_odevzdani`, `nadoba`, `obdobi_od`, `obdobi_do`, `predchozi_pocet` |
| `Σ Celkem` | `167 ×` | rozpis podle komodit, `predchozi_celkem` |

Diagnostika se na stránce zařízení řadí podle abecedy. Názvy jsou zvolené
tak, aby nahoře byl MESOH rok (číslice jsou v abecedě před písmeny), pod ním
čas aktualizace, pak komodity a úplně dole součet (`Σ` je za všemi písmeny).

Řádek s rokem (`sensor.<obec>_obdobi_odevzdani`) se 1. října přepne sám,
název i stav. Počty mají ID `sensor.<obec>_odevzdano_<komodita>` a součet
`sensor.<obec>_odevzdano_celkem`. Rok v ID ani v názvu nemají — ID se po
vzniku nemění a graf by u historie ukazoval letošní rok i u loňských dat.
Období je u každého počtu i v atributech `obdobi_od` a `obdobi_do`.

### Přechod na nový MESOH rok

Web má výběr období (`?year=…`) a po přihlášení ukazuje poslední
**vyhodnocené** období. 1. října je to tedy pořád loňský rok, protože nový
ještě hodnocení nemá. Integrace se proto řídí datem:

- **probíhající rok** je období ze seznamu, do kterého patří dnešek — podle
  něj se počítá *Konec MESOH roku*, odpočet a období u počtů
- **počty odevzdání** se berou ze svezeného odpadu na nástěnce jen za
  probíhající období, takže v novém roce začnou od nuly. Konečný stav
  uzavřeného roku je u každého počtu v atributu `predchozi_pocet`, u součtu
  v `predchozi_celkem`
- **poplatek** patří k probíhajícímu roku — výsledek 2026/27 určí poplatek
  na rok 2028. Dokud ho web nespočítá (ukazuje „? Kč"), jsou senzory
  poplatku **neznámé** s atributem `stav: zatím nevyhodnoceno`; loňská cena
  zůstává v atributech `predchozi_rok` a `predchozi_poplatek`. Neznámé,
  ne nula — nula by se zapsala do statistik a graf vývoje ceny by měl
  každý říjen falešný propad.

  V textu oznámení se to dá ošetřit šablonou:

  ```jinja
  {% set c = states('sensor.<obec>_predpokladany_poplatek') %}
  Aktuální cena: {{ c ~ ' Kč' if c | is_number else 'zatím neznámá' }}
  ```
- **skóre, využití a objem na osobu** taky patří k probíhajícímu roku. Dokud
  ho web nevyhodnotí (nástěnka i hodnocení pořád ukazují loňský rok), jsou
  **neznámé** a loňský výsledek je v atributech `predchozi_hodnota`,
  `predchozi_obdobi_od` a `predchozi_obdobi_do`
- **body za komoditu** (atribut `eko_body` u počtů) se ukazují jen u
  komodit, které se v probíhajícím roce už odevzdaly

Na loňská čísla se dá dál dívat i v grafu. Všechny tyhle senzory ukládají
dlouhodobé statistiky, takže graf ukazuje loňský průběh až do 1. října,
pak krátkou mezeru a od vyhodnocení nového roku nové hodnoty. Dlouhodobé
statistiky HA nemaže — nastavení `purge_keep_days` se týká jen podrobné
historie stavů, ne jich.

Atribut `eko_body` říká, kolik bodů dalo poslední odevzdání té komodity
(plast 3,4, papír 3…). Při každém stažení se hledá nejnovější záznam na
nástěnce i v tabulce za celý MESOH rok, takže když obec bodování změní,
uvidíš to po kliknutí na počet.

## Karta: přehled svozů

> [!IMPORTANT]
> `<obec>` v příkladech nahraď svou obcí — přesné názvy entit najdeš
> ve Vývojářských nástrojích → Stavy (filtr `odevzdani`, resp. `poplatek`).

Komodity, souhrny a poplatek v jedné kartě. Komodity se do ní doplňují samy
a řadí se podle nejbližšího svozu, takže kartu není potřeba upravovat, když
obec komoditu přidá, přejmenuje nebo přestane svážet (třeba papír a plast
zvlášť nahradí společný svoz „Papír, Plast“). Potřebuje z HACS kartu
[auto-entities](https://github.com/thomasloven/lovelace-auto-entities).

```yaml
type: custom:auto-entities
show_empty: true
card:
  type: entities
  title: Svoz odpadu
filter:
  template: |-
    {#- Komodity, které mají ještě svoz, podle nejbližšího svozu; pod nimi pevné řádky. -#}
    {%- set dev = device_id('sensor.<obec>_pristi_svoz') -%}
    {%- set zarizeni = (device_attr(dev, 'name_by_user') or device_attr(dev, 'name')) ~ ' ' -%}
    {%- set ns = namespace(svozy=[], radky=[]) -%}
    {%- for e in device_entities(dev) | select('match', 'sensor\.') -%}
      {%- if state_attr(e, 'harmonogram') is not none and state_attr(e, 'days_to') is not none -%}
        {%- set ns.svozy = ns.svozy + [{'e': e, 'n': state_attr(e, 'friendly_name') | replace(zarizeni, ''), 'd': state_attr(e, 'days_to') | int(999)}] -%}
      {%- endif -%}
    {%- endfor -%}
    {%- for s in ns.svozy | sort(attribute='n') | sort(attribute='d') -%}
      {%- set ns.radky = ns.radky + [{'entity': s.e, 'name': s.n}] -%}
    {%- endfor -%}
    {%- set ns.radky = ns.radky + [
      {'type': 'divider'},
      {'entity': 'sensor.<obec>_posledni_odevzdani', 'name': 'Poslední odevzdání'},
      {'entity': 'sensor.<obec>_pristi_svoz', 'name': 'Příští svoz'},
      {'type': 'divider'},
      {'entity': 'sensor.<obec>_predpokladany_poplatek', 'name': 'Po úlevě', 'icon': 'mdi:cash'},
      {'entity': 'sensor.<obec>_sazba_poplatku', 'name': 'Sazba'},
      {'entity': 'sensor.<obec>_uleva_mesoh', 'name': 'Úleva MESOH'},
      {'entity': 'sensor.<obec>_uleva_v_procentech', 'name': 'Úleva'}
    ] -%}
    {{ ns.radky }}
```

Komodity karta pozná podle atributů `harmonogram` a `days_to`, které mají jen
senzory svozů komodit, a bere je ze zařízení služby (proto stačí
`sensor.<obec>_pristi_svoz` na jednom místě). Pevné řádky pod nimi jsou
obyčejný seznam: tlačítko ruční aktualizace se přidá jako
`{'entity': 'button.<obec>_aktualizovat'}`.

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

Upozornění na nová odevzdání. Po každém obnovení, při kterém na nástěnce
něco přibylo, vyvolá integrace jednu událost `mojeodpadky_nova_odevzdani` se
seznamem všeho nového v `zaznamy`. Pytle se na webu načítají každý zvlášť
(čtyři pytle plastu jsou čtyři stejné řádky), v seznamu jsou sloučené do
jednoho řádku s počtem `pocet` a součtem bodů `ekobody_celkem`. Co už
integrace viděla, si pamatuje i přes restart Home Assistantu, takže se nic
neohlásí dvakrát a naopak se po restartu ohlásí i to, co přibylo, zatímco
Home Assistant neběžel. Hned po instalaci (nemá s čím srovnávat) mlčí.

Jedna zpráva za obnovení:

```yaml
automation:
  - alias: Zapsáno na nástěnce
    triggers:
      - trigger: event
        event_type: mojeodpadky_nova_odevzdani
    actions:
      - action: notify.mobile_app
        data:
          message: >-
            {{ trigger.event.data.ucet }}:
            {%- for z in trigger.event.data.zaznamy %}
            • {{ z.komodita }} ({{ z.nadoba }}) {{ z.datum }}
            {%- if z.pocet > 1 %} · {{ z.pocet }}×{% endif %}
            {%- if z.ekobody_celkem is not none %} · {{ z.ekobody_celkem }} b{% endif %}
            {%- endfor %}
```

Každý řádek v `zaznamy` má `datum` (ISO), `komodita`, `nadoba`, `pocet`,
`ekobody` (body za jeden kus) a `ekobody_celkem`; událost navíc `pocet`
(všech nových řádků), `ucet` (název služby) a `entry_id`. Při víc účtech
jde automatizaci omezit jen na jeden:

```yaml
    triggers:
      - trigger: event
        event_type: mojeodpadky_nova_odevzdani
        event_data:
          ucet: Nová Lhota (jiny_login)
```

Pro každý jednotlivý řádek nástěnky zvlášť je dál i událost
`mojeodpadky_odevzdano` (`datum`, `komodita`, `nadoba`, `ekobody`, `ucet`,
`entry_id`); u víc pytlů přijde víckrát.

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

- **Výběr v Home Assistantu platí.** Harmonogram zaškrtnutý v Home Assistantu
  integrace na webu přihlásí; když ho na webu zrušíš, při další obnově ho
  přihlásí znovu. Odhlašuje ale jen při změně výběru v Home Assistantu: odběr
  přidaný na webu nechá být a prázdný výběr ignoruje — aby rozejitý stav nebo
  chyba v nastavení neodhlásila odběr, o který nikdo nepřišel dobrovolně.
- **Přelom roku:** obec vypíše nové harmonogramy s novými ID a staré zmizí.
  Web často sám přihlásí odběratele i na nový ročník. Integrace si u
  vybraných harmonogramů pamatuje komoditu a místní část a výběr převede na
  letošní obdobu; harmonogram, který zmizel bez nástupce (obec třeba papír
  a plast nahradí tříděným odpadem), z výběru vyřadí. Přepínače upozornění
  i senzory komodit se srovnají samy.
- **Nastavení ukazuje stav webu.** Ve výběru harmonogramů je zaškrtnuté to,
  co je na webu opravdu přihlášené (i to, co přihlásil sám web), ne výběr
  z doby instalace. Odhlásí se jen to, co v něm sám odškrtneš.
- Po zapnutí e-mailových upozornění se výsledek ověřuje; když server zapne
  upozornění jinde, přepínač to ohlásí jako chybu.
- **Změněné heslo:** když server uložené heslo odmítne, Home Assistant nabídne
  v **Nastavení → Zařízení a služby** zadat nové. Službu není třeba mazat.
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

Testy nad Home Assistantem (načtení integrace, průvodce, opětovné přihlášení,
nastavení) potřebují balíček `pytest-homeassistant-custom-component`; bez něj
se přeskočí:

```bash
pytest tests/ -o asyncio_mode=auto
```

## Přístup k datům

Data poskytuje [mojeodpadky.cz](https://www.mojeodpadky.cz). Integrace je
neoficiální a s provozovatelem služby nemá žádný vztah.

Integrace se přihlašuje uživatelskými údaji a čte běžné stránky webu.
Nepoužívá žádné neveřejné rozhraní.

Data se obnovují podle nastaveného intervalu, standardně každých šest hodin.
Jedno obnovení stáhne svozový kalendář a první stránku nástěnky; další stránky
nástěnky jen tehdy, když se záznamy probíhajícího MESOH roku na první
nevejdou, a veřejnou stránku obce jednou kvůli jejímu názvu. Hodnocení
stanoviště a inventura se berou jen tehdy, když na nástěnce přibude nový
záznam, nebo nejvýš jednou za den — hodnocení má skoro megabajt a mění se
právě jen po svozu.

Logo v záhlaví patří provozovateli mojeodpadky.cz.

Pokud si provozovatel nepřeje, aby integrace existovala, otevřete prosím
[issue](https://github.com/joazif/ha-mojeodpadky/issues) — repozitář bude
stažen.
