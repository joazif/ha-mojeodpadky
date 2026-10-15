# Změny

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
