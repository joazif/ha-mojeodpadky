# Změny

## Nevydáno

### Změněno

- README: karta „Přehled svozů“ je automatická (auto-entities). Komodity se
  doplňují samy a řadí podle nejbližšího svozu, takže kartu není potřeba
  upravovat, když obec komoditu přidá, přejmenuje nebo přestane svážet.

## 0.1.3 – 2026-10-20

### Opraveno

- Přepínače upozornění u harmonogramů, jejichž název je celý velkými písmeny
  (třeba „Harmonogram BIO … 2027“, „Harmonogram TŘÍDĚNÝ ODPAD … 2027“), se
  jmenovaly celým názvem harmonogramu i s rokem. Komodita se teď bere ze
  svozů v kalendáři, kde ji web píše vždy stejně („Bio“, „Papír, Plast“).
  Přepínač se jmenuje jen podle ní a víc sledovaných harmonogramů téže
  komodity ovládá jeden. Přepínače ze starší verze se převedou (entity_id
  s rokem se jednou přejmenuje) a přepínač komodity, kterou už žádný
  sledovaný harmonogram nemá, se odstraní.
- Společný svoz víc komodit („Papír, Plast“) má ikonu recyklace místo
  popelnice.
- Senzor svozu komodity, která už nemá žádný další svoz (třeba papír a plast
  zvlášť po přechodu na společný svoz), zmizí, místo aby ukazoval „Neznámý“.
  Když se svozy komodity znovu objeví, vrátí se se stejným ID.
- Nastavení harmonogramů ukazovalo výběr z doby instalace, ne skutečný stav
  webu. Harmonogramy, které web přihlásil sám (třeba nový ročník), v něm
  nebyly zaškrtnuté a uložení formuláře po jakékoli změně by je na webu
  odhlásilo. Teď je zaškrtnuté to, co je na webu opravdu přihlášené.
- Harmonogram, který z webu zmizel bez nástupce, se z výběru vyřadí, místo
  aby při každém obnovení psal do logu varování.
- Harmonogram, který z webu zmizel bez nástupce (loňský ročník komodity, kterou
  obec od nového roku sváží jinak), se už nepokouší při každém obnovení znovu
  přihlásit.

## 0.1.2 – 2026-10-20

### Přidáno

- Opětovné přihlášení po změně hesla. Když server uložené heslo odmítne (při
  startu i později za běhu), Home Assistant zastaví stahování a v **Nastavení →
  Zařízení a služby** nabídne zadat nové heslo. Ověří ho a integraci znovu
  načte; dřív šlo heslo opravit jen smazáním a novým přidáním služby.

### Změněno

- Vyžaduje Home Assistant 2024.11 nebo novější (koordinátor dostává config
  entry výslovně, což starší verze neumí).
- Spojení se serverem vytváří Home Assistant (`async_create_clientsession`),
  pro každý účet vlastní, s vlastními cookies. Home Assistant ho sám uklidí při
  uvolnění služby; průvodce si bere vlastní a po ověření ho odpojí. Požadavky
  dál nesou User-Agent integrace s odkazem na repozitář.
- Integrace už sama nenastavuje `entity_id`. Nové entity dostanou stejná ID jako
  dosud (`sensor.<obec>_odevzdano_<komodita>`, `…_odevzdano_celkem`,
  `…_obdobi_odevzdani`) přes navržené ID, které pak vlastní registr Home
  Assistantu. Stávající entity se nemění a přejmenování uživatelem platí.
- Přepínače upozornění už nemají v atributech e-mail z webu: atributy vidí
  každý uživatel Home Assistantu a ukládají se do historie i záloh.
- Velká stránka hodnocení stanoviště se zpracovává mimo smyčku událostí Home
  Assistantu.
- Názvy „Σ Celkem“ a „Období“ jsou v překladech (anglicky „Σ Total“, „Period“),
  ne napevno v kódu.
- Nastavení (options flow) a opětovné přihlášení používají aktuální API Home
  Assistantu (`self.config_entry`, `_get_reauth_entry`).
- README: opravené popisy, které neodpovídaly kódu (zrušený odběr na webu se
  podle výběru v Home Assistantu přihlásí znovu, upozornění jsou po komoditách,
  kalendář má svozy jako události, co všechno se při obnovení stahuje).
- Testy nad Home Assistantem pro průvodce, opětovné přihlášení, nastavení
  a celé načtení integrace včetně ID entit a User-Agentu (`tests/test_reauth.py`,
  `test_config_flow.py`, `test_setup.py`).
- README: instalace začíná vyhledáním v HACS, vlastní repozitář je jen záloha.

### Opraveno

- Odmítnuté heslo se dřív hlásilo jako výpadek serveru, takže to Home Assistant
  donekonečna zkoušel znovu se starým heslem.
- Vypršení časového limitu spojení se nehlásilo jako chyba spojení: v průvodci
  skončilo neznámou chybou a při stahování výpisem chyby do logu.
- Každá chyba webu během obnovy dat se teď hlásí jako dočasná nedostupnost.
  Dřív některé (třeba poškozená data kalendáře) končily neočekávanou chybou.
- Průvodce přidáním zavírá spojení se serverem i tehdy, když je účet už
  nastavený nebo průvodce zavřeš uprostřed. Neočekávanou chybu ohlásí místo
  pádu.
- Nastavení služby, která není načtená, se neotevře s prázdným seznamem
  harmonogramů (uložením by se výběr smazal), ale řekne proč.
- Integrace se znovu načítá jen při skutečné změně výběru nebo intervalu. Dřív
  se načetla i při převodu harmonogramů na nový rok (uprostřed stahování)
  a po zadání nového hesla dvakrát.
- Kalendář nevracel svoz začínající přesně na konci dotazovaného rozsahu.

## 0.1.1 – 2026-10-15

### Změněno

- Událost `mojeodpadky_odevzdano` si pamatuje naposledy vídané záznamy nástěnky
  i přes restart Home Assistantu. Dřív se po restartu první stažení ztišilo, takže
  se záznam, který přibyl za dobu, kdy Home Assistant neběžel, neohlásil nikdy.
  Teď se ohlásí, a to, co už se ohlásilo, se podruhé neopakuje. Automatizace tak
  nepotřebuje vlastní paměť (např. `input_text`).
- Po smazání služby se uklidí i uložený stav (výběr a vídané záznamy).

## 0.1.0 – 2026-10-03

### Změněno

- Požadavky na mojeodpadky.cz mají v hlavičce User-Agent odkaz na
  repozitář integrace, aby provozovatel webu věděl, odkud přicházejí.

### Opraveno

- Logo v README se nezobrazovalo v HACS. HACS nepodporuje `<picture>` ani
  relativní cesty k obrázkům; logo má teď absolutní odkaz na
  `raw.githubusercontent.com`.
