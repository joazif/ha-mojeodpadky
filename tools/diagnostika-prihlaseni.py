#!/usr/bin/env python3
"""Diagnostika přihlášení na mojeodpadky.cz.

Projde stejnou cestu jako integrace a vypíše, co server vrací:

    python3 tools/diagnostika-prihlaseni.py

Na jméno a heslo se zeptá. Heslo se při psaní nezobrazuje, nikam se neukládá
ani nevypisuje. V automatizovaném prostředí jde místo ptaní použít proměnné
MOJEODPADKY_LOGIN a MOJEODPADKY_PASSWORD.

Výstup je bezpečné poslat dál - obsahuje jen názvy stránek, počty a adresy.
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
UA = "Mozilla/5.0 (compatible; HomeAssistant mojeodpadky diagnostika)"

RE_SIGNIN = re.compile(r'id="frm-signInForm"')
RE_SIGNOUT = re.compile(r"do=signOut|/odhlasit|Odhlásit", re.I)
RE_TITLE = re.compile(r"<title>(.*?)</title>", re.S | re.I)
RE_SLUG_LINK = re.compile(
    r'href="(?:https://www\.mojeodpadky\.cz)?/([a-z0-9-]{2,})/'
    r"(?:svozovy-kalendar|nastenka|sberna-mista|moje-nadoby)"
)
RE_ANY_LINK = re.compile(r'href="/([a-z0-9-]{3,})/([a-z0-9-]+)"')
RE_EVENTS = re.compile(r'id="collectionScheduleCalendar"[^>]*?\sdata-events="([^"]*)"')


def zprava(popis: str, hodnota) -> None:
    print(f"  {popis:.<42} {hodnota}")


def otevri(opener, url: str, data: dict | None = None) -> tuple[str, str]:
    payload = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=payload, headers={"User-Agent": UA,
                                                             "Referer": f"{BASE}/"})
    with opener.open(req, timeout=45) as resp:
        return resp.read().decode("utf-8", "replace"), resp.geturl()


def main() -> int:
    login = os.environ.get("MOJEODPADKY_LOGIN")
    password = os.environ.get("MOJEODPADKY_PASSWORD")

    if not login or not password:
        if not sys.stdin.isatty():
            print(
                "Skript potřebuje jméno a heslo. Spusť ho v terminálu, nebo nastav "
                "MOJEODPADKY_LOGIN a MOJEODPADKY_PASSWORD.",
                file=sys.stderr,
            )
            return 2
        print("Přihlašovací údaje na mojeodpadky.cz (heslo nebude vidět):\n")
        if login:
            # Ať je jasné, odkud se jméno vzalo - jinak to vypadá,
            # že se skript na půlku údajů zapomněl zeptat.
            maska = login[0] + "*" * max(len(login) - 1, 1)
            print(f"  Jméno beru z proměnné MOJEODPADKY_LOGIN: {maska}")
            print("  (když je špatné: unset MOJEODPADKY_LOGIN a spusť znovu)")
        else:
            login = input("  Přihlašovací jméno: ").strip()
        password = password or getpass.getpass("  Heslo: ")
        print()

    if not login or not password:
        print("Bez jména a hesla se nedá nic zjistit.", file=sys.stderr)
        return 2

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    print("1) GET homepage (kvůli session)")
    body, url = otevri(opener, f"{BASE}/")
    zprava("cílová adresa", url)
    zprava("přihlašovací formulář", bool(RE_SIGNIN.search(body)))
    zprava("cookies", [c.name for c in jar])

    print("\n2) POST přihlášení")
    body, url = otevri(opener, f"{BASE}/", {
        "login": login,
        "password": password,
        "_submit": "Přihlásit",
        "_do": "signInForm-submit",
    })
    titulek = RE_TITLE.search(body)
    zprava("cílová adresa", url)
    zprava("titulek stránky", titulek.group(1).strip() if titulek else "-")
    zprava("velikost odpovědi", f"{len(body)} znaků")
    zprava("formulář pořád na stránce", bool(RE_SIGNIN.search(body)))
    zprava("stopa po odhlášení", bool(RE_SIGNOUT.search(body)))
    zprava("cookies", [c.name for c in jar])

    slug = None
    cesta = urllib.parse.urlparse(url).path.strip("/").split("/")
    if cesta and cesta[0]:
        slug = cesta[0]
        zprava("obec z adresy", slug)
    odkaz = RE_SLUG_LINK.search(body)
    if odkaz:
        slug = slug or odkaz.group(1)
        zprava("obec z odkazu", odkaz.group(1))
    if not odkaz and not slug:
        zprava("jiné odkazy na stránce", sorted({f"/{a}/{b}" for a, b in
                                                RE_ANY_LINK.findall(body)})[:10] or "žádné")

    if not slug:
        print("\nObec se nepodařilo zjistit - pošli výpis výš.")
        return 1

    print(f"\n3) GET /{slug}/svozovy-kalendar")
    body, url = otevri(opener, f"{BASE}/{slug}/svozovy-kalendar")
    titulek = RE_TITLE.search(body)
    zprava("cílová adresa", url)
    zprava("titulek stránky", titulek.group(1).strip() if titulek else "-")
    zprava("data-events na stránce", bool(RE_EVENTS.search(body)))
    zprava("formulář pořád na stránce", bool(RE_SIGNIN.search(body)))

    print("\n3b) Formuláře na stránce kalendáře")
    kam_kal = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "kalendar.local.html")
    with open(kam_kal, "w", encoding="utf-8") as f:
        f.write(body)

    def bez_udaju(text: str) -> str:
        text = re.sub(r"[A-Za-z0-9._%+-]+(@|&#64;|&commat;)[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
                      "<email>", text)
        return " ".join(text.split())

    for m in re.finditer(r"<form[^>]*>", body):
        print("   formulář:", bez_udaju(m.group(0))[:160])
    for m in re.finditer(r'<input[^>]*type="hidden"[^>]*>', body):
        print("   skryté pole:", bez_udaju(m.group(0))[:160])
    for m in re.finditer(r'<input[^>]*type="submit"[^>]*>', body):
        print("   tlačítko:", bez_udaju(m.group(0))[:160])
    for m in list(re.finditer(r"js-notification-form", body))[:2]:
        print("   upozornění:", bez_udaju(body[max(0, m.start()-260):m.start()+220])[-420:])
    for m in re.finditer(r'class="modal[^"]*"[^>]*id="([^"]+)"', body):
        print("   modál:", m.group(1))
    print(f"   stránka uložena do {kam_kal}")

    print(f"\n4) GET /{slug}/nastenka")
    body, url = otevri(opener, f"{BASE}/{slug}/nastenka?collectionsListPageSize=20")
    titulek = RE_TITLE.search(body)
    zprava("cílová adresa", url)
    zprava("titulek stránky", titulek.group(1).strip() if titulek else "-")
    celkem = re.search(r"ze\s+([\d\s\u00a0]+?)\s*z[áa]znam",
                       " ".join(re.sub(r"<[^>]+>", " ", body).split()), re.I)
    zprava("hláška o počtu záznamů", celkem.group(0) if celkem else "nenalezena")

    print("\n5) Rozbor tabulek na nástěnce")
    tabulky = re.findall(r"<table\b.*?</table>", body, re.S | re.I)
    zprava("počet tabulek", len(tabulky))
    for poradi, tabulka in enumerate(tabulky, 1):
        radky = re.findall(r"<tr\b[^>]*>(.*?)</tr>", tabulka, re.S | re.I)
        print(f"\n   tabulka {poradi}: {len(radky)} řádků")
        for popis, radek in (("hlavička", radky[0] if radky else ""),
                             ("první řádek", radky[1] if len(radky) > 1 else "")):
            bunky = [" ".join(re.sub(r"<[^>]+>", " ", b).replace("\u00a0", " ").split())
                     for b in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", radek,
                                         re.S | re.I)]
            print(f"     {popis}: {bunky if bunky else 'žádné buňky'}")

    if not tabulky:
        # Tabulka může být poskládaná z divů, ne z <table>.
        divy = re.findall(r'class="[^"]*(?:datatable|m-table)[^"]*"', body, re.I)
        zprava("místo tabulek našel", sorted(set(divy))[:5] or "nic")

    print("\n6) Poplatek za odpady")
    text = " ".join(re.sub(r"<[^>]+>", " ", body).split())
    nalez = re.search(r"Poplatek za odpady.{0,600}", text, re.I)
    if nalez:
        print("   " + nalez.group(0))
    else:
        zprava("zmínka o poplatku", "nenalezena")
        for slovo in ("MESOH", "sazba", "úlev"):
            m = re.search(rf".{{0,120}}{slovo}.{{0,200}}", text, re.I)
            if m:
                print(f"   [{slovo}] " + m.group(0))

    kam = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nastenka.local.html")
    with open(kam, "w", encoding="utf-8") as f:
        f.write(body)
    print(f"\nStránka uložena do {kam}")
    print("(git ji ignoruje - *.local.html; posílej ji jen vědomě, jsou v ní tvoje data)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
