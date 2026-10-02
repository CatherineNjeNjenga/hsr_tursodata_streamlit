import os
import re
import requests
import feedparser
from bs4 import BeautifulSoup

# ---------- CONFIG ----------
TURSO_URL = os.environ["TURSO_URL"].replace("libsql://", "https://") + "/v2/pipeline"
TURSO_TOKEN = os.environ["TURSO_TOKEN"]

RSS_FEED_URL = "https://feeds.megaphone.fm/FLIGHTSTUDIOGROUPLTD3349407104"

USER_AGENT = "HSR-Scraper/1.0 (+https://hotsmartrich.com)"


# ---------- FETCH ----------
def fetch_page(url):
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text


# ---------- DISCOVERY ----------
def discover_episode_urls():
    print(f"Fetching RSS feed: {RSS_FEED_URL}")
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(RSS_FEED_URL, headers=headers, timeout=30)
    resp.raise_for_status()
    feed = feedparser.parse(resp.text)

    print(f"  Feed title: {feed.feed.get('title', 'UNKNOWN')}")
    print(f"  Total entries found: {len(feed.entries)}")

    # Print the first 3 links so we can see the format
    for entry in feed.entries[:3]:
        print(f"  Sample link: {entry.get('link', 'NO LINK')}")
        print(f"  Sample guid: {entry.get('id', 'NO GUID')}")
        print(f"  Sample title: {entry.get('title', 'NO TITLE')}")

    urls = []
    for entry in feed.entries:
        link = entry.get("link", "").strip()
        if link:
            urls.append(link)

    # Dedupe
    seen = set()
    unique = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)

    return unique


# ---------- PARSE ----------
def parse_episode(html, url):
    soup = BeautifulSoup(html, "html.parser")

    # Header metadata
    header_spans = soup.select("span._11r14xt1")
    title = header_spans[0].get_text(strip=True) if len(header_spans) > 0 else ""
    date = header_spans[2].get_text(strip=True) if len(header_spans) > 2 else ""

    # Guest name from the "X's Top 10" heading
    body_text = soup.get_text(" ", strip=True)
    guest_name = ""
    m = re.search(r"([A-Z][a-zA-Z'\-]+(?:\s[A-Z][a-zA-Z'\-]+)?)'s Top 10", body_text)
    if m:
        guest_name = m.group(1)

    # Recommendations: every ShopMy link on the page
    all_links = soup.find_all("a", href=True)
    shopmy_links = [a for a in all_links if "shopmy" in a["href"].lower()]

    rows = []
    for i, link in enumerate(shopmy_links, start=1):
        product_name = link.get_text(strip=True)
        product_link = link["href"]

        parent_span = link.find_parent("span", class_="hxnnnr0")
        description = ""
        if parent_span:
            next_p = parent_span.find_next("p")
            if next_p:
                desc_span = next_p.find("span", class_="hxnnnr0")
                if desc_span:
                    description = desc_span.get_text(strip=True)

        rows.append({
            "row_id": i,
            "guest_name": guest_name,
            "guest_role": "Guest",
            "episode_date": date,
            "episode_title": title,
            "product_name": product_name,
            "product_link": product_link,
            "link_type": "ShopMy",
            "link_status": "Active",
            "guest_description": description,
            "source_url": url,
        })

    return rows


# ---------- TURSO ----------
def turso_execute(sql, args=None):
    stmt = {"sql": sql}
    if args:
        stmt["args"] = args
    payload = {
        "requests": [
            {"type": "execute", "stmt": stmt},
            {"type": "close"},
        ]
    }
    headers = {"Authorization": f"Bearer {TURSO_TOKEN}"}
    r = requests.post(TURSO_URL, json=payload, headers=headers, timeout=60)
    r.raise_for_status()
    return r.json()


def get_scraped_urls():
    """Return the set of source_urls already in the recommendations table."""
    result = turso_execute("SELECT DISTINCT source_url FROM recommendations")
    try:
        rows = result["results"][0]["response"]["result"]["rows"]
        return {row[0] for row in rows if row and row[0]}
    except (KeyError, IndexError, TypeError):
        return set()


def insert_rows_batch(rows):
    """Insert all rows in one Turso pipeline request."""
    if not rows:
        return

    sql = """
    INSERT INTO recommendations
      (row_id, guest_name, guest_role, episode_date, product_name,
       product_link, link_type, link_status, guest_description, source_url)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(row_id, source_url) DO NOTHING
    """

    requests_list = []
    for row in rows:
        args = [
            {"type": "integer", "value": str(row["row_id"])},
            {"type": "text",    "value": row["guest_name"]},
            {"type": "text",    "value": row["guest_role"]},
            {"type": "text",    "value": row["episode_date"]},
            {"type": "text",    "value": row["product_name"]},
            {"type": "text",    "value": row["product_link"]},
            {"type": "text",    "value": row["link_type"]},
            {"type": "text",    "value": row["link_status"]},
            {"type": "text",    "value": row["guest_description"]},
            {"type": "text",    "value": row["source_url"]},
        ]
        requests_list.append({
            "type": "execute",
            "stmt": {"sql": sql, "args": args},
        })

    requests_list.append({"type": "close"})

    payload = {"requests": requests_list}
    headers = {"Authorization": f"Bearer {TURSO_TOKEN}"}
    r = requests.post(TURSO_URL, json=payload, headers=headers, timeout=120)
    r.raise_for_status()
    return r.json()


# ---------- MAIN ----------
if __name__ == "__main__":
    print("Discovering episodes from RSS feed...")
    all_urls = discover_episode_urls()
    print(f"  Found {len(all_urls)} episodes in feed")

    if not all_urls:
        raise SystemExit("RSS feed returned no episodes — aborting.")

    print("Checking which episodes are already in Turso...")
    already_scraped = get_scraped_urls()
    print(f"  {len(already_scraped)} episodes already in database")

    new_urls = [u for u in all_urls if u not in already_scraped]
    print(f"  {len(new_urls)} new episodes to scrape")

    if not new_urls:
        print("Nothing new to scrape. Done.")
        raise SystemExit(0)

    all_rows = []
    for url in new_urls:
        print(f"Scraping {url}")
        try:
            html = fetch_page(url)
            rows = parse_episode(html, url)
            print(f"  Parsed {len(rows)} rows")
            all_rows.extend(rows)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

    if not all_rows:
        print("No rows parsed from any episode. Done.")
        raise SystemExit(0)

    print(f"Inserting {len(all_rows)} rows into Turso...")
    insert_rows_batch(all_rows)
    print(f"Done. Inserted rows from {len(new_urls)} episodes.")
