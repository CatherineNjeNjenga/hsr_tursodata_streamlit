import os
import re
import requests
from bs4 import BeautifulSoup

# ---------- CONFIG ----------
TURSO_URL = os.environ["TURSO_URL"].replace("libsql://", "https://") + "/v2/pipeline"
TURSO_TOKEN = os.environ["TURSO_TOKEN"]

PODCAST_LISTING_URL = "https://hotsmartrich.com/t/podcast"
BASE_URL = "https://hotsmartrich.com"
USER_AGENT = "HSR-Scraper/1.0 (+https://hotsmartrich.com)"


# ---------- FETCH ----------
def fetch_page(url):
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text


# ---------- DISCOVERY ----------
def discover_episode_urls():
    """Scrape the HSR podcast listing page and return all /p/ episode URLs."""
    print(f"Fetching listing page: {PODCAST_LISTING_URL}")
    html = fetch_page(PODCAST_LISTING_URL)
    soup = BeautifulSoup(html, "html.parser")

    urls = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/p/") and "podcast" not in href:
            urls.append(BASE_URL + href)

    seen = set()
    unique = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)

    print(f"  Found {len(unique)} episodes on listing page")
    return unique


# ---------- PARSE ----------
def parse_episode(html, url):
    soup = BeautifulSoup(html, "html.parser")

    # --- Header metadata ---
    header_spans = soup.select("span._11r14xt1")
    title = header_spans[0].get_text(strip=True) if len(header_spans) > 0 else ""
    date = header_spans[2].get_text(strip=True) if len(header_spans) > 2 else ""

    # --- Guest name from "X's Top 10" heading ---
    body_text = soup.get_text(" ", strip=True)
    guest_name = ""
    m = re.search(r"([A-Z][a-zA-Z'\-]+(?:\s[A-Z][a-zA-Z'\-]+)?)'s Top 10", body_text)
    if m:
        guest_name = m.group(1)

    # --- Locate the recommendations section ---
    top10_match = re.search(
        r"Top 10(.*?)(?:Favourite Part|Something That People|Hot, Smart, Rich|Reply|$)",
        body_text,
        re.DOTALL | re.IGNORECASE,
    )
    top10_text = top10_match.group(1) if top10_match else ""

    # --- Extract numbered items: "01. ...", "02. ..." ---
    items = re.findall(
        r"(\d{2})\.\s+(.+?)(?=\s*\d{2}\.\s+|$)",
        top10_text,
        re.DOTALL,
    )

    # --- Find all <a> links on the page, indexed by their visible text ---
    page_links = []
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        if text:
            page_links.append((text.lower(), a["href"]))

    rows = []
    for i, (num, description) in enumerate(items, start=1):
        description = re.sub(r"\s+", " ", description).strip()

        # Extract product name: text before the first descriptive verb
        product_name = re.split(
            r"\s+(?:is|are|gives|makes|means|helps|lets|keeps|means)\s+",
            description,
            maxsplit=1,
        )[0].strip()

        # Try to match a link whose visible text appears in the description
        product_link = ""
        link_type = "None"
        link_status = "Placeholder"

        for text, href in page_links:
            if text in description.lower() or text in product_name.lower():
                product_link = href
                link_status = "Active"
                if "shopmy" in href.lower():
                    link_type = "ShopMy"
                elif "amzn" in href.lower():
                    link_type = "Amazon"
                else:
                    link_type = "Direct"
                break

        rows.append({
            "row_id": i,
            "guest_name": guest_name,
            "guest_role": "Guest",
            "episode_date": date,
            "product_name": product_name,
            "product_link": product_link,
            "link_type": link_type,
            "link_status": link_status,
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
    print(f"  Turso response status: {r.status_code}")
    response_json = r.json()
    for result in response_json.get("results", []):
        if "error" in result or result.get("type") == "error":
            print(f"  Turso error: {result}")
    r.raise_for_status()
    return response_json


# ---------- MAIN ----------
if __name__ == "__main__":
    print("Discovering episodes from listing page...")
    all_urls = discover_episode_urls()

    if not all_urls:
        raise SystemExit("Listing page returned no episode URLs — aborting.")

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
