"""Konstanty integrace mojeodpadky.cz."""

DOMAIN = "mojeodpadky"

CONF_SLUG = "slug"
CONF_SCHEDULES = "schedules"
CONF_NOTIFICATION = "notification"
# Harmonogramy, u kterých má web posílat e-mailová upozornění.
CONF_NOTIFY = "notify_schedules"

CONF_SCAN_INTERVAL = "scan_interval_hours"
# Jak často se stahují data. Web se mění nanejvýš jednou denně,
# hodinový interval je spíš pro netrpělivé.
SCAN_INTERVAL_CHOICES = (1, 3, 6, 24)
DEFAULT_SCAN_INTERVAL_HOURS = 6

# Kolik posledních odevzdání držíme v atributu senzoru.
COLLECTED_LIMIT = 15
# Kolik řádků si vyžádáme od serveru - s rezervou, aby se limit naplnil
# i kdyby pár řádků parserem neprošlo. Povolené hodnoty jsou 5/10/20/50/100.
COLLECTED_PAGE_SIZE = 20

ATTR_DAYS_TO = "days_to"
ATTR_SCHEDULE = "harmonogram"
ATTR_TYPES = "types"
ATTR_DATE = "datum"
ATTR_WASTE_TYPE = "komodita"
ATTR_CONTAINER = "nadoba"
ATTR_RECORDS = "zaznamy"
ATTR_POINTS = "ekobody"

# Událost pro automatizace - vyvolá se pro každé nové odevzdání,
# které na nástěnce přibylo od minulého obnovení.
EVENT_COLLECTED = "mojeodpadky_odevzdano"
