"""Test parserů proti markupu zkopírovanému ze skutečné stránky."""

import importlib.util
import pathlib
import sys
from datetime import date

# api.py nacitame primo, aby se netahal cely balicek (ten importuje homeassistant).
_API = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "mojeodpadky" / "api.py"
_spec = importlib.util.spec_from_file_location("mojeodpadky_api", _API)
_api = importlib.util.module_from_spec(_spec)
sys.modules["mojeodpadky_api"] = _api
_spec.loader.exec_module(_api)
MojeOdpadkyClient = _api.MojeOdpadkyClient
CollectedItem = _api.CollectedItem
diff_collected = _api.diff_collected

_TEXTS = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "mojeodpadky" / "texts.py"
_tspec = importlib.util.spec_from_file_location("mojeodpadky_texts", _TEXTS)
_texts = importlib.util.module_from_spec(_tspec)
sys.modules["mojeodpadky_texts"] = _texts
_tspec.loader.exec_module(_texts)

BODY = (pathlib.Path(__file__).parent / "fixture_kalendar.html").read_text("utf-8")
NASTENKA = (pathlib.Path(__file__).parent / "fixture_nastenka.html").read_text("utf-8")
HODNOCENI = (pathlib.Path(__file__).parent / "fixture_hodnoceni.html").read_text("utf-8")
INVENTURA = (pathlib.Path(__file__).parent / "fixture_inventura.html").read_text("utf-8")

EXPECTED_SCHEDULES = [
    (8001, "Harmonogram směsný odpad 2026", True, 90001, date(2026, 1, 5), date(2026, 12, 28)),
    (8006, "Harmonogram bioodpad NOVÁ LHOTA A OSTATNÍ ČÁSTI 2026", True, 90002, date(2026, 3, 19), date(2026, 11, 26)),
    (8005, "Harmonogram papír NOVÁ LHOTA + ZÁHOŘÍ 2026", True, 90003, date(2026, 1, 6), date(2026, 12, 22)),
    (8004, "Harmonogram plast  NOVÁ LHOTA + ZÁHOŘÍ 2026", True, 90004, date(2026, 1, 6), date(2026, 12, 22)),
    (8002, "Harmonogram plast OSTATNÍ ČÁSTI 2025", False, None, date(2026, 1, 7), date(2026, 12, 23)),
    (8003, "Harmonogram papír OSTATNÍ ČÁSTI 2025", False, None, date(2026, 1, 7), date(2026, 12, 23)),
    (8007, "Harmonogram bioodpad ZÁHOŘÍ 2026", False, None, date(2026, 3, 24), date(2026, 12, 1)),
]

failures = []


def check(label, got, want):
    if got != want:
        failures.append(f"{label}: cekano {want!r}, dostal {got!r}")
    print(f"  {'ok ' if got == want else 'CHYBA'} {label}")


print("parse_schedules")
schedules = MojeOdpadkyClient.parse_schedules(BODY)
check("pocet harmonogramu", len(schedules), 7)
for got, want in zip(schedules, EXPECTED_SCHEDULES):
    check(
        f"harmonogram {want[0]}",
        (got.schedule_id, got.name, got.subscribed, got.subscribe_id, got.date_from, got.date_to),
        want,
    )
check("sledovanych", sum(s.subscribed for s in schedules), 4)
check("kratky nazev pro prepinac",
      [s.short_name for s in schedules[:4]],
      ["Směsný odpad", "Bioodpad", "Papír", "Plast"])
check("mistni cast pro rozliseni",
      [s.area for s in schedules if "bioodpad" in s.name.lower()],
      ["Nová", "Záhoří"])
check("smesny zadnou mistni cast nema",
      next(s.area for s in schedules if s.schedule_id == 8001), "")
check("upozorneni zapnuta jen u prvniho",
      [s.schedule_id for s in schedules if s.notifications], [8001])
check("nesledovany nema upozorneni",
      any(s.notifications for s in schedules if not s.subscribed), False)

print("rozliseni stejnych komodit")
Schedule = _api.Schedule
distinguish = _api.distinguish


def _nazev(item, sada):
    """Stejná logika, jakou používá přepínač upozornění.

    Porovnává se se všemi harmonogramy obce, i s nesledovanými - název
    entity se nemá měnit podle toho, co je zrovna zaškrtnuté.
    """
    stejne = [x for x in sada if x is not item and x.short_name == item.short_name]
    rozliseni = distinguish(item, stejne)
    if rozliseni and rozliseni.lower() not in item.short_name.lower():
        return f"Upozornění: {item.short_name} {rozliseni}"
    return f"Upozornění: {item.short_name}"


def _sada(*nazvy):
    return [Schedule(schedule_id=100 + i, name=n, subscribed=True)
            for i, n in enumerate(nazvy)]


mistni = _sada("Harmonogram bioodpad NOVÁ LHOTA A OSTATNÍ ČÁSTI 2026",
               "Harmonogram bioodpad ZÁHOŘÍ 2026")
check("mistni cast velkymi pismeny", [_nazev(x, mistni) for x in mistni],
      ["Upozornění: Bioodpad Nová", "Upozornění: Bioodpad Záhoří"])

rocniky = _sada("Harmonogram papír 2025", "Harmonogram papír 2026")
check("stary a novy rocnik", [_nazev(x, rocniky) for x in rocniky],
      ["Upozornění: Papír 2025", "Upozornění: Papír 2026"])

casti = _sada("Harmonogram plast - Horní Ves", "Harmonogram plast - Dolní Ves")
check("obec bez velkych pismen se nezdvojuje", [_nazev(x, casti) for x in casti],
      ["Upozornění: Plast - Horní Ves", "Upozornění: Plast - Dolní Ves"])

shodne = _sada("Harmonogram sklo", "Harmonogram sklo")
check("uplne shodne nazvy rozlisi ID", [_nazev(x, shodne) for x in shodne],
      ["Upozornění: Sklo 100", "Upozornění: Sklo 101"])

samotny = _sada("Harmonogram papír NOVÁ LHOTA + ZÁHOŘÍ 2026")
check("jediny harmonogram zustane kratky", _nazev(samotny[0], samotny),
      "Upozornění: Papír")

nesledovany = [
    Schedule(schedule_id=200, name="Harmonogram bioodpad NOVÁ LHOTA 2026",
             subscribed=True),
    Schedule(schedule_id=201, name="Harmonogram bioodpad ZÁHOŘÍ 2026",
             subscribed=False),
]
check("rozlisi i proti nesledovanemu",
      _nazev(nesledovany[0], nesledovany), "Upozornění: Bioodpad Nová")

print("prelom roku")
fingerprint = _api.fingerprint
find_successor = _api.find_successor

loni = _sada("Harmonogram směsný odpad 2026",
             "Harmonogram papír NOVÁ LHOTA + ZÁHOŘÍ 2026",
             "Harmonogram bioodpad ZÁHOŘÍ 2026")
letos = [
    Schedule(schedule_id=900, name="Harmonogram směsný odpad 2027", subscribed=False),
    Schedule(schedule_id=901, name="Harmonogram papír NOVÁ LHOTA + ZÁHOŘÍ 2027",
             subscribed=False),
    Schedule(schedule_id=902, name="Harmonogram bioodpad ZÁHOŘÍ 2027",
             subscribed=False),
]
check("otisk letopocet ignoruje",
      fingerprint(loni[0]) == fingerprint(letos[0]), True)
check("nastupce smesneho", find_successor(fingerprint(loni[0]), letos, set()), 900)
check("nastupce papiru", find_successor(fingerprint(loni[1]), letos, set()), 901)
check("nastupce bioodpadu podle mistni casti",
      find_successor(fingerprint(loni[2]), letos, set()), 902)
check("uz obsazeny nastupce se nenabidne",
      find_successor(fingerprint(loni[0]), letos, {900}), None)
check("zruseny harmonogram nastupce nema",
      find_successor("sklo|", letos, set()), None)
check("jina mistni cast se neplete",
      find_successor(fingerprint(Schedule(schedule_id=1,
                                          name="Harmonogram bioodpad NOVÁ LHOTA 2026",
                                          subscribed=True)), letos, set()), None)

print("parse_events")
events = MojeOdpadkyClient.parse_events(BODY)
check("pocet svozu", len(events), 125)
check("serazeno podle data", [e.day for e in events], sorted(e.day for e in events))
check("prvni svoz", (events[0].day, events[0].waste_type), (date(2026, 1, 5), "Směsný odpad"))
check("posledni svoz", (events[-1].day, events[-1].waste_type), (date(2026, 12, 28), "Směsný odpad"))
check("komodity", sorted({e.waste_type for e in events}), ["Bio", "Papír", "Plast", "Směsný odpad"])

bio = [e.day for e in events if e.waste_type == "Bio"]
check("bio pocet", len(bio), 21)
# Server posila 5.11. a 19.11. az za 26.11.; parser je musi zaradit na misto.
check("bio listopadove svozy navic serazene", bio[-4:],
      [date(2026, 11, 5), date(2026, 11, 12), date(2026, 11, 19), date(2026, 11, 26)])
check("bio posledni", bio[-1], date(2026, 11, 26))
check("bio obsahuje 5.11. a 19.11.", (date(2026, 11, 5) in bio, date(2026, 11, 19) in bio), (True, True))
check("nazev harmonogramu u svozu", events[0].schedule_name, "Harmonogram směsný odpad 2026")
check("dvojita mezera u plastu srovnana",
      next(e.schedule_name for e in events if e.waste_type == "Plast"),
      "Harmonogram plast NOVÁ LHOTA + ZÁHOŘÍ 2026")

print("parse_default_email")
check("email odescapovan", MojeOdpadkyClient.parse_default_email(BODY), "uzivatel@example.com")

print("ucet bez sledovanych harmonogramu")
jen_karty = (
    '<div class="m-portlet m-portlet--mobile"><div class="m-portlet__head">'
    '<h3 class="m-portlet__head-text">Harmonogram papír 2026</h3></div>'
    '<a href="" class="btn js-subscribe-form" data-id="555" '
    'data-label="Harmonogram papír 2026">Začít sledovat</a></div>'
)
check("stranka bez svozu ale s kartami je kalendar",
      MojeOdpadkyClient._is_calendar(jen_karty), True)
check("prihlasovaci stranka neni kalendar",
      MojeOdpadkyClient._is_calendar('<form id="frm-signInForm"></form>' + jen_karty),
      False)
check("prazdna stranka neni kalendar", MojeOdpadkyClient._is_calendar("<html></html>"),
      False)
check("harmonogramy se z ni prectou",
      [(h.schedule_id, h.subscribed) for h in MojeOdpadkyClient.parse_schedules(jen_karty)],
      [(555, False)])
check("svozy jsou prazdne", MojeOdpadkyClient.parse_events(jen_karty), [])

print("prazdna stranka")
check("zadne harmonogramy", MojeOdpadkyClient.parse_schedules("<html></html>"), [])
check("zadne svozy", MojeOdpadkyClient.parse_events("<html></html>"), [])

print("parse_collected")
collected = MojeOdpadkyClient.parse_collected(NASTENKA)
check("pocet zaznamu", len(collected), 8)
check("nejnovejsi prvni", [item.day for item in collected],
      sorted((item.day for item in collected), reverse=True))
check("prvni zaznam",
      (collected[0].day, collected[0].waste_type, collected[0].container, collected[0].points),
      (date(2026, 9, 19), "Elektro", "Sběrný dvůr", "1"))
check("druhy zaznam tyz den",
      (collected[1].day, collected[1].waste_type, collected[1].container, collected[1].points),
      (date(2026, 9, 19), "Kovy", "Sběrný dvůr", "0"))
check("kod nadoby", (collected[2].waste_type, collected[2].container), ("Papír", "1AB"))
check("nedelitelna mezera srovnana", collected[6].container, "Sběrný dvůr")
check("tabulka nadob ani mesicni prehled se nepletou",
      sorted({item.waste_type for item in collected}),
      ["Dřevo", "Elektro", "Kovy", "Papír", "Plast", "Pneumatiky", "Suť"])
check("dva stejne zaznamy v jeden den zustanou oba",
      sum(1 for item in collected if item.day == date(2026, 9, 12)), 2)
check("klic zaznamu", collected[0].key, (date(2026, 9, 19), "Elektro", "Sběrný dvůr"))

check("past - podrobnosti svozu se nezapocitaly",
      [item.waste_type for item in collected].count("Elektro"), 1)

print("parse_fee")
poplatek = MojeOdpadkyClient.parse_fee(NASTENKA)
check("rok", poplatek.year, 2027)
check("sazba", poplatek.rate, 1500)
check("uleva", poplatek.discount, 450)
check("uleva v procentech", poplatek.discount_percent, 30.0)
check("po uleve", poplatek.total, 1050)
check("desetinna carka v procentech",
      MojeOdpadkyClient.parse_fee(
          "Poplatek za odpady na rok 2027 Předpokládaná sazba poplatku na osobu: "
          "1 200 Kč Předpokládaná úleva MESOH z poplatku na osobu: 300 Kč (25,5 %) "
          "Předpokládaný poplatek po odečtení úlevy MESOH na osobu: 900 Kč"
      ).discount_percent, 25.5)
check("tisice s mezerou v sazbe",
      MojeOdpadkyClient.parse_fee(
          "Poplatek za odpady na rok 2027 Předpokládaná sazba poplatku na osobu: "
          "1 200 Kč Předpokládaný poplatek po odečtení úlevy MESOH na osobu: 900 Kč"
      ).rate, 1200)
check("stranka bez poplatku", MojeOdpadkyClient.parse_fee("<html></html>"), None)

print("parse_rating")
hodnoceni = MojeOdpadkyClient.parse_rating(HODNOCENI)
check("objem na osobu", hodnoceni.volume_person, 4200.0)
check("smesny na osobu", hodnoceni.mixed_person, 610.5)
check("tridene na osobu", hodnoceni.sorted_person, 3589.5)
check("pocet osob z posledniho mesice", hodnoceni.people, 4)
check("obdobi", (hodnoceni.period_from, hodnoceni.period_to),
      (date(2025, 10, 1), date(2026, 9, 30)))
check("objem stanoviste se neplete s objemem na osobu",
      hodnoceni.volume_person != 12600.0, True)
check("stranka bez hodnoceni", MojeOdpadkyClient.parse_rating("<html></html>"), None)
check("objem bez rozpadu",
      MojeOdpadkyClient.parse_rating("Celkový obsloužený objem/osoba 900 litrů").volume_person,
      900.0)

print("parse_people")
check("pocet osob z inventury", MojeOdpadkyClient.parse_people(INVENTURA), 4)
check("nespletl si poplatniky",
      MojeOdpadkyClient.parse_people("Počet poplatníků 9 Počet osob 4"), 4)
check("stranka bez inventury", MojeOdpadkyClient.parse_people("<html></html>"), None)

print("parse_score")
skore = MojeOdpadkyClient.parse_score(NASTENKA)
check("ziskane body", skore.points, 42.5)
check("maximum bodu", skore.max_points, 110.5)
check("vyuziti v procentech", skore.percent, 38.5)
check("dopocet procent bez hlasky",
      MojeOdpadkyClient.parse_score("Celkem EKO bodů/osoba 55 z 110").percent, 50.0)
check("stranka bez skore", MojeOdpadkyClient.parse_score("<html></html>"), None)

print("parse_collected_total")
check("celkem zaznamu", MojeOdpadkyClient.parse_collected_total(NASTENKA), 747)
check("chybejici hlaska", MojeOdpadkyClient.parse_collected_total("<html></html>"), None)
check("tisice s mezerou",
      MojeOdpadkyClient.parse_collected_total("Zobrazeno 10 ze <b>1 234</b> záznamů"), 1234)

print("odolnost parseru")
check("neplatne datum radek preskoci",
      MojeOdpadkyClient.parse_collected(
          "<table><tr><th>Datum</th><th>Komodita</th><th>Označení nádoby</th>"
          "<th>EKO body</th></tr>"
          "<tr><td>31.02.2026</td><td>Papír</td><td>1AB</td><td>1</td></tr>"
          "<tr><td>16.09.2026</td><td>Papír</td><td>1AB</td><td>1</td></tr></table>"),
      [CollectedItem(date(2026, 9, 16), "Papír", "1AB", "1")])
check("predpripraveny text da stejny vysledek",
      (MojeOdpadkyClient.parse_fee(NASTENKA, _api.page_text(NASTENKA)),
       MojeOdpadkyClient.parse_score(NASTENKA, _api.page_text(NASTENKA)),
       MojeOdpadkyClient.parse_collected_total(NASTENKA, _api.page_text(NASTENKA))),
      (MojeOdpadkyClient.parse_fee(NASTENKA),
       MojeOdpadkyClient.parse_score(NASTENKA),
       MojeOdpadkyClient.parse_collected_total(NASTENKA)))
check("hodnoceni s predpripravenym textem",
      MojeOdpadkyClient.parse_rating(HODNOCENI, _api.page_text(HODNOCENI)),
      MojeOdpadkyClient.parse_rating(HODNOCENI))

print("prazdna nastenka")
check("zadne zaznamy", MojeOdpadkyClient.parse_collected("<html></html>"), [])
check("tabulka bez datovych radku",
      MojeOdpadkyClient.parse_collected(
          "<table><tr><th>Datum</th><th>Komodita</th><th>Označení nádoby</th>"
          "<th>EKO body</th></tr></table>"), [])

print("parse_town")
# Titulek opsany ze skutecne (verejne) stranky /novalhota.
check("obec z titulku",
      MojeOdpadkyClient.parse_town("<title>Aktuality Nová Lhota | Moje odpadky</title>"),
      "Nová Lhota")
check("jina obec",
      MojeOdpadkyClient.parse_town("<title>Aktuality Nový Knín | Moje odpadky</title>"),
      "Nový Knín")
check("titulek bez obce",
      MojeOdpadkyClient.parse_town("<title>Svozový kalendář | Moje odpadky</title>"), None)
check("chybova stranka",
      MojeOdpadkyClient.parse_town("<title>Chyba 404 - interní chyba systému | MOJE ODPADKY</title>"),
      None)
check("html entity v titulku",
      MojeOdpadkyClient.parse_town("<title>Aktuality Brand&#253;s | Moje odpadky</title>"),
      "Brandýs")
check("stranka bez titulku", MojeOdpadkyClient.parse_town("<html></html>"), None)

print("diff_collected")
minule = collected[:]
check("beze zmeny nic nehlasi", diff_collected(minule, collected), [])
novy = CollectedItem(date(2026, 9, 21), "Sklo", "3AB", "2")
check("jeden novy zaznam", diff_collected(minule, [novy] + minule), [novy])
dalsi_elektro = CollectedItem(date(2026, 9, 19), "Elektro", "Sběrný dvůr", "1")
check("druhe odevzdani teze komodity v tyz den",
      diff_collected(minule, [dalsi_elektro] + minule), [dalsi_elektro])
check("prvni stazeni mlci", diff_collected([], collected), [])
check("vypadek nastenky nic nehlasi", diff_collected(minule, []), [])
check("kratsi seznam nic nehlasi", diff_collected(minule, minule[:3]), [])

print("popisky stavu")
check("dnes", _texts.relative_future(0), "Dnes")
check("zitra", _texts.relative_future(1), "Zítra")
check("za 3 dny", _texts.relative_future(3), "Za 3 dny")
check("za 5 dni", _texts.relative_future(5), "Za 5 dní")
check("za 15 dni", _texts.relative_future(15), "Za 15 dní")
check("odevzdano dnes", _texts.relative_past(0), "Dnes")
check("odevzdano vcera", _texts.relative_past(1), "Včera")
check("odevzdano pred 5 dny", _texts.relative_past(5), "Před 5 dny")

print()
if failures:
    print(f"NEPROSLO: {len(failures)}")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("vsechny kontroly prosly")
