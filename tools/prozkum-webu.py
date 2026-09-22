#!/usr/bin/env python3
"""Projde všechny stránky přihlášeného účtu a vypíše, co na nich je.

    python3 tools/prozkum-webu.py

Na jméno a heslo se zeptá, heslo není vidět a nikam se neukládá. U každé
stránky vypíše nadpisy, tabulky, formuláře a čísla s popiskem. E-maily a kódy
nádob maskuje, takže výstup je bezpečné poslat dál. Stránky se ukládají
do tools/*.local.html, ty jsou v .gitignore a obsahují osobní údaje.
"""

from __future__ import annotations

import getpass
import http.cookiejar
import os
import re
import sys
import urllib.parse
import urllib.request

BASE = "https://www.mojeodpadky.cz"
UA = "Mozilla/5.0 (compatible; HomeAssistant mojeodpadky pruzkum)"

STRANKY = [
    ("aktuality", ""),
    ("nastenka", "/nastenka"),
    ("svozovy-kalendar", "/svozovy-kalendar"),
    ("upozorneni-udalosti", "/upozorneni-udalosti"),
    ("inventura-stanoviste", "/inventura-stanoviste"),
    ("odpadovy-dotaznik", "/odpadovy-dotaznik"),
    ("hodnoceni-stanoviste", "/hodnoceni-stanoviste"),
    ("eko-nakupovani", "/eko-nakupovani"),
    ("dokumenty", "/dokumenty"),
    ("nastaveni", "/nastaveni"),
]

RE_TITLE = re.compile(r"<title>(.*?)</title>", re.S | re.I)
RE_HEADING = re.compile(r"<h[1-5][^>]*>(.*?)</h[1-5]>", re.S | re.I)
RE_PORTLET = re.compile(r'm-portlet__head-text[^>]*>(.*?)</h3>', re.S)
RE_TABLE = re.compile(r"<table\b.*?</table>", re.S | re.I)
RE_ROW = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S | re.I)
RE_CELL = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.S | re.I)
RE_FORM = re.compile(r'<form[^>]*id="([^"]+)"[^>]*>', re.I)
RE_DO = re.compile(r'name="_do" value="([^"]+)"')
# "Neco: 123", "Neco: 12,5 %", "Neco: 1 200 Kc"
RE_HODNOTA = re.compile(r"([A-ZÁ-Ž][^:<>]{3,60}):\s*([\d\s.,]+\s*(?:%|Kč|l|litrů|bodů)?)")


def maskuj(text: str) -> str:
    text = re.sub(
        r"[A-Za-z0-9._%+-]+(@|&#64;|&commat;)[A-Za-z0-9.-]{0,40}", "<email>", text
    )
    text = re.sub(r"\b[A-Z]{2,4}\d{6,}\b", "<kod>", text)
    return " ".join(text.split())


def text(html: str) -> str:
    return maskuj(re.sub(r"<[^>]+>", " ", html).replace(" ", " "))


def main() -> int:
    login = os.environ.get("MOJEODPADKY_LOGIN")
    password = os.environ.get("MOJEODPADKY_PASSWORD")
    if not (login and password):
        if not sys.stdin.isatty():
            print("Spusť v terminálu, nebo nastav MOJEODPADKY_LOGIN a _PASSWORD.",
                  file=sys.stderr)
            return 2
        print("Přihlašovací údaje na mojeodpadky.cz (heslo nebude vidět):\n")
        login = login or input("  Přihlašovací jméno: ").strip()
        password = password or getpass.getpass("  Heslo: ")
        print()

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def otevri(url: str, data: dict | None = None) -> tuple[str, str]:
        payload = urllib.parse.urlencode(data).encode() if data else None
        req = urllib.request.Request(
            url, data=payload, headers={"User-Agent": UA, "Referer": f"{BASE}/"}
        )
        with opener.open(req, timeout=45) as resp:
            return resp.read().decode("utf-8", "replace"), resp.geturl()

    otevri(f"{BASE}/")
    telo, url = otevri(f"{BASE}/", {
        "login": login, "password": password,
        "_submit": "Přihlásit", "_do": "signInForm-submit",
    })
    cesta = urllib.parse.urlparse(url).path.strip("/").split("/")
    slug = cesta[0] if cesta and cesta[0] else None
    if not slug:
        print("Přihlášení neprošlo.", file=sys.stderr)
        return 1
    print(f"Obec: {slug}\n")

    kam = os.path.dirname(os.path.abspath(__file__))

    for nazev, cesta_str in STRANKY:
        url = f"{BASE}/{slug}{cesta_str}"
        try:
            telo, _ = otevri(url)
        except Exception as err:  # noqa: BLE001 - průzkum, chyba nesmí zastavit zbytek
            print(f"=== {nazev} === nedostupné: {err}\n")
            continue

        with open(os.path.join(kam, f"{nazev}.local.html"), "w", encoding="utf-8") as f:
            f.write(telo)

        titulek = RE_TITLE.search(telo)
        print(f"=== {nazev}  ({len(telo)} znaků) ===")
        print("  titulek:", maskuj(titulek.group(1)) if titulek else "-")

        nadpisy = []
        for regex in (RE_PORTLET, RE_HEADING):
            for m in regex.finditer(telo):
                t = text(m.group(1))
                if t and len(t) < 80 and t not in nadpisy and "cookie" not in t.lower():
                    nadpisy.append(t)
        if nadpisy:
            print("  nadpisy:", " | ".join(nadpisy[:12]))

        tabulky = RE_TABLE.findall(telo)
        for poradi, tabulka in enumerate(tabulky, 1):
            radky = RE_ROW.findall(tabulka)
            if not radky:
                continue
            hlavicka = [text(b) for b in RE_CELL.findall(radky[0])]
            prvni = [text(b) for b in RE_CELL.findall(radky[1])] if len(radky) > 1 else []
            print(f"  tabulka {poradi} ({len(radky)} řádků): {hlavicka}")
            if prvni:
                print(f"      první řádek: {prvni}")

        formulare = [(f, RE_DO.findall(telo)) for f in RE_FORM.findall(telo)]
        jmena = [f for f, _ in formulare if "cookie" not in f.lower()]
        if jmena:
            print("  formuláře:", ", ".join(jmena[:6]))

        cely = text(telo)
        hodnoty = []
        for m in RE_HODNOTA.finditer(cely):
            popis, hodnota = m.group(1).strip(), m.group(2).strip()
            if hodnota and popis.lower() not in ("e-mail", "heslo"):
                dvojice = f"{popis}: {hodnota}"
                if dvojice not in hodnoty:
                    hodnoty.append(dvojice)
        for dvojice in hodnoty[:10]:
            print("  údaj:", dvojice[:110])
        print()

    print(f"Stránky uložené do {kam}/*.local.html (git je ignoruje).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
