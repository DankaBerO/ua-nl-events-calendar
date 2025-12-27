import requests
from bs4 import BeautifulSoup
from dateutil import parser
import pytz
from ics import Calendar, Event
from datetime import timedelta
from collections import defaultdict

TZ = pytz.timezone("Europe/Amsterdam")

# --- Источники (пока берём ExpatInfoHolland: 2 табличные страницы) ---
SOURCES = [
    {
        "name": "ExpatInfoHolland – Networking Events",
        "url": "https://expatinfoholland.nl/events/netherlands-networking-events/",
        "category": "networking",
        "parser": "expatinfo_table",
    },
    {
        "name": "ExpatInfoHolland – Workshops & Training",
        "url": "https://expatinfoholland.nl/events/netherlands-workshops-training/",
        "category": "workshops_upskilling",
        "parser": "expatinfo_table",
    },
]

# --- Как будут называться выходные файлы ICS ---
CATEGORY_TO_ICS = {
    "networking": "networking.ics",
    "workshops_upskilling": "workshops_upskilling.ics",
    # запасной вариант
    "other": "other.ics",
}

def parse_expatinfo_table(source):
    """
    Парсер для ExpatInfoHolland, где события в таблице:
    EVENT TYPE | ORGANIZATION | CITY | DATE | LOCATION
    Берём только строки, где DATE можно распарсить в конкретную дату.
    """
    html = requests.get(source["url"], headers={"User-Agent": "Mozilla/5.0"}, timeout=30).text
    soup = BeautifulSoup(html, "html.parser")

    table = soup.find("table")
    if not table:
        return []

    events = []
    rows = table.find_all("tr")
    for tr in rows:
        cols = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if len(cols) < 5:
            continue

        # пропускаем заголовок
        if "EVENT TYPE" in cols[0].upper() or "ORGANIZATION" in cols[1].upper():
            continue

        event_type, org, city, date_text, location = cols[0], cols[1], cols[2], cols[3], cols[4]

        # ссылка обычно в колонке ORGANIZATION
        a = tr.find("a")
        url = a.get("href") if a else source["url"]

        # пробуем распарсить дату
        start = None
        try:
            dt = parser.parse(date_text, fuzzy=True, dayfirst=True)
            if dt.tzinfo is None:
                dt = TZ.localize(dt)
            start = dt
        except Exception:
            start = None

        # правило: без конкретной даты — пропускаем (Every Mon / 1st Tue etc)
        if start is None:
            continue

        # title: Организация (тип) — Город
        title = f"{org} ({event_type}) — {city}".strip()

        events.append({
            "title": title,
            "start": start,
            "end": None,
            "location": location,
            "url": url,
            "source": source["name"],
            "category": source.get("category", "other"),
        })

    return events

def export_ics(events, filename):
    cal = Calendar()
    for e in events:
        ev = Event()
        ev.name = e["title"]

        ev.begin = e["start"]
        # если нет end — по умолчанию 1 час
        ev.end = (e["end"] if e["end"] else (e["start"] + timedelta(hours=1)))

        ev.location = e.get("location") or ""
        ev.url = e.get("url") or ""
        ev.description = f"Source: {e.get('source')}\n{e.get('url')}"

        cal.events.add(ev)

    with open(filename, "w", encoding="utf-8") as f:
        f.writelines(cal.serialize_iter())

def main():
    all_events = []
    for s in SOURCES:
        print(f"Fetching: {s['name']}")

        if s.get("parser") == "expatinfo_table":
            evs = parse_expatinfo_table(s)
        else:
            evs = []

        print(f"  Found with dates: {len(evs)}")
        all_events.extend(evs)

    # группируем по категориям
    by_cat = defaultdict(list)
    for e in all_events:
        by_cat[e.get("category", "other")].append(e)

    # экспортируем отдельный ICS на каждую категорию
    for cat, events in by_cat.items():
        events.sort(key=lambda x: x["start"])
        out_name = CATEGORY_TO_ICS.get(cat, f"{cat}.ics")
        out_path = f"docs/{out_name}"
        export_ics(events, out_path)
        print(f"  Exported: {out_path} ({len(events)} events)")


    print("\nDONE: ICS files created in current folder")

if __name__ == "__main__":
    main()
