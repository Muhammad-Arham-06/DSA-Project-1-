"""Scraper (Wikipedia + BeautifulSoup) and CSV helpers."""
import csv
import os
import re
import time

import requests
from bs4 import BeautifulSoup

COLUMNS = ["title", "year", "month", "day", "production_company",
           "director", "cast", "cast_count", "title_length"]
NUM_COLS = {"year", "day", "cast_count", "title_length"}

START_YEAR = 1930
END_YEAR = 2026

HEADERS = {
    "User-Agent": "DSA-Project1-MoviesExplorer/1.0 (university student project)",
    "Accept-Language": "en-US,en;q=0.9",
}
MONTHS = {"january", "february", "march", "april", "may", "june", "july",
          "august", "september", "october", "november", "december"}
CAST_NAMES = ["Cast and crew", "Cast", "Starring", "Cast members", "Main cast"]

os.makedirs("pages", exist_ok=True)               # downloaded pages are cached here


def clean(text):
    text = re.sub(r"\[[^\]]*\]", "", text)        # remove references like [ 2 ]
    text = re.sub(r"\s+,", ",", text)             # "Name , Name" -> "Name, Name"
    return re.sub(r"\s+", " ", text).strip()


def split_people(text):
    """Extract director and cast from 'Name (director); Name (screenplay); Actor1, Actor2'."""
    parts = [p.strip() for p in text.split(";") if p.strip()]
    director = ""
    cast = ""
    for p in parts:
        if "(director" in p:
            director = p.split("(director")[0].strip(" ,")
            break
    if parts and "(" not in parts[-1]:
        cast = parts[-1]
    return director, cast


def make_row(title, year, month, day, company, director, cast):
    cast_count = len([c for c in cast.split(",") if c.strip()]) if cast else 0
    return {
        "title": title,
        "year": year,
        "month": month or "Unknown",
        "day": day if day else 0,
        "production_company": company or "Unknown",
        "director": director or "Unknown",
        "cast": cast,
        "cast_count": cast_count,
        "title_length": len(title),
    }


def make_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def get_html(year, session):
    path = f"pages/{year}.html"
    if os.path.exists(path):                      # reuse the page if it is already downloaded
        with open(path, encoding="utf-8") as f:
            return f.read()

    url = f"https://en.wikipedia.org/wiki/List_of_American_films_of_{year}"
    for attempt in range(6):
        r = session.get(url, timeout=30)
        if r.status_code == 200:
            with open(path, "w", encoding="utf-8") as f:
                f.write(r.text)
            time.sleep(3)                         # be polite to the server
            return r.text
        if r.status_code == 429:
            retry_after = r.headers.get("Retry-After", "")
            wait = int(retry_after) if retry_after.isdigit() else 30 * (attempt + 1)
            print(f"  {year}: 429 (rate limited), waiting {wait} seconds...")
            time.sleep(wait)
            continue
        print(f"  {year}: page not found, status {r.status_code}")
        return None
    print(f"  {year}: repeated 429 errors, skipping this year")
    return None


def parse_new_format(table, year):
    """Header: Opening | Title | Production company | Cast and crew"""
    out = []
    month, day = "", 0
    for tr in table.select("tr")[1:]:
        raw = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
        while raw and clean(raw[-1]) == "":       # drop the empty reference cell
            raw.pop()
        if len(raw) < 3:
            continue

        # counting from the right: title, company, cast and crew; month/day (if any) come first
        title, company, people = raw[-3], raw[-2], raw[-1]
        for item in raw[:-3]:
            name = "".join(item.split()).lower()
            if name in MONTHS:
                month = name.title()
            else:
                m = re.search(r"\d+", item)
                if m:
                    day = int(m.group())

        title = clean(title)
        if not title or title == "Title":
            continue
        director, cast = split_people(clean(people))
        out.append(make_row(title, year, month, day, clean(company), director, cast))
    return out


def parse_old_format(table, header, year):
    """Header: Title | Director | Cast | Genre | Notes (columns are found by their header names)"""
    out = []
    idx = {name: i for i, name in enumerate(header)}
    cast_col = next((idx[n] for n in CAST_NAMES if n in idx), None)

    for tr in table.select("tr")[1:]:
        cells = tr.find_all(["th", "td"])
        if len(cells) != len(header):             # skip irregular rows (rowspan)
            continue
        texts = [clean(c.get_text(" ", strip=True)) for c in cells]
        title = texts[idx["Title"]]
        if not title or title == "Title":
            continue
        director = texts[idx["Director"]]
        cast = texts[cast_col] if cast_col is not None else ""
        out.append(make_row(title, year, "", 0, "", director, cast))
    return out


def parse_page(html, year):
    soup = BeautifulSoup(html, "lxml")
    result = []
    for table in soup.select("table.wikitable"):
        all_rows = table.select("tr")
        if not all_rows:
            continue
        header = [clean(c.get_text(" ")) for c in all_rows[0].find_all(["th", "td"])]
        if "Title" in header and "Cast and crew" in header:
            result.extend(parse_new_format(table, year))
        elif "Title" in header and "Director" in header:
            result.extend(parse_old_format(table, header, year))
    return result


def scrape_year(year, session):
    html = get_html(year, session)
    if html is None:
        return []
    result = parse_page(html, year)
    print(f"{year}: {len(result)} films")
    return result


def scrape_url(url, session):
    """Scrape a single page given by URL (the year is guessed from the URL)."""
    r = session.get(url, timeout=30)
    r.raise_for_status()
    m = re.search(r"(?:18|19|20)\d{2}", url)
    year = int(m.group()) if m else 0
    return parse_page(r.text, year)


def row_key(row):
    return (row["title"], row["year"], row["month"], row["day"])


def save_csv(rows, path):
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def load_movies(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            for c in NUM_COLS:
                r[c] = int(r[c])
            rows.append(r)
    return rows