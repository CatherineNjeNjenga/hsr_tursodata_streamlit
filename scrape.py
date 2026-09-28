import os
import re
import requests
from bs4 import BeautifulSoup

# ---------- CONFIG ----------
# Read secrets from GitHub Actions environment
TURSO_URL = os.environ["TURSO_URL"].replace("libsql://", "https://") + "/v2/pipeline"
TURSO_TOKEN = os.environ["TURSO_TOKEN"]

# Episode pages to scrape
EPISODE_URLS = [
    "https://hotsmartrich.com/p/the-ai-strategy-that-runs-my-business",
]


# ---------- FETCH ----------
def fetch_page(url):
    headers = {"User-Agent": "Mozilla/5.0 (compatible; HSR-Scraper/1.0)"}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text


# ---------- PARSE ----------
def parse_episode(html, url):
    soup = BeautifulSoup(html, "html.parser")

    # Header metadata
    header_spans = soup.select("span._11r14xt1")
    title = header_spans[0].get_text(strip=True) if len(header_spans) > 0 else ""
    subtitle = header_spans[1].get_text(strip=True) if len(header_spans) > 1 else ""
    date = header_spans[2].get_text(strip=True) if len(header_spans) > 2 else ""

    # Recommendations container
    top10 = soup.select_one("div#sophias-top-10")
    if not top10:
        print(f"WARNING: no #sophias-top-10 found on {url}")
        return []

    # Guest name/role live above the top-10 block
    header_html = str(soup).split('id="sophias-top-10"')[0]
    header_soup = BeautifulSoup(header_html, "html.parser")
    guest_spans = header_soup.select("span.hxnnnr0")
    guest_name = guest_spans[0].get_text(strip=True) if len(guest_spans) > 0 else ""
    guest_role = guest_spans[1].get_text(strip=True) if len(guest_spans) > 1 else ""

    # Each recommendation block
    blocks = top10.select("div.j6zgbu0")
    rows = []
    for i, block in enumerate(blocks, start=1):
        spans = block.select("span.hxnnnr0")
        if len(spans) < 4:
            continue

        product_span = spans[2]
        link_tag = product_span.find("a", href=True)
        product_name = product_span.get_text(strip=True)
        product_link = link_tag["href"] if link_tag else ""
        description = spans[3].get_text(strip=True)

        # Classify link type
        if "shopmy" in product_link:
            link_type = "ShopMy"
        elif product_link:
            link_type = "Direct"
        else:
            link_type = "None"

        rows.append({
            "row_id": i,
            "guest_name": guest_name,
            "guest_role": "Guest",
            "episode_date": date,
            "product_name": product_name,
            "product_link": product_link,
            "link_type": link_type,
            "link_status": "Active" if product_link else "Placeholder",
            "guest_description": description,
            "source_url": url,
        })

    return rows


# ---------- WRITE TO TURSO ----------
def turso_execute(sql, args):
    payload = {
        "requests": [
            {"type": "execute", "stmt": {"sql": sql, "args": args}},
            {"type": "close"},
        ]
    }
    headers = {"Authorization": f"Bearer {TURSO_TOKEN}"}
    r = requests.post(TURSO_URL, json=payload, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


def insert_rows(rows):
    sql = """
    INSERT INTO recommendations
      (row_id, guest_name, guest_role, episode_date, product_name,
       product_link, link_type, link_status, guest_description, source_url)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(row_id, source_url) DO NOTHING
    """
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
        turso_execute(sql, args)


# ---------- MAIN ----------
if __name__ == "__main__":
    all_rows = []
    for url in EPISODE_URLS:
        print(f"Scraping {url}")
        html = fetch_page(url)
        rows = parse_episode(html, url)
        print(f"  Parsed {len(rows)} rows")
        all_rows.extend(rows)

    if len(all_rows) < 3:
        raise SystemExit(f"Only parsed {len(all_rows)} rows — refusing to write.")

    insert_rows(all_rows)
    print(f"Done. Inserted {len(all_rows)} rows.")
