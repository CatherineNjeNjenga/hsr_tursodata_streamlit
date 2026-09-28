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

    # --- Header metadata ---
    header_spans = soup.select("span._11r14xt1")
    title = header_spans[0].get_text(strip=True) if len(header_spans) > 0 else ""
    date = header_spans[2].get_text(strip=True) if len(header_spans) > 2 else ""

    # --- Guest name/role (from page body, before Top 10 section) ---
    body_text = soup.get_text(" ", strip=True)
    guest_name = ""
    guest_role = "Guest"
    # Look for a heading pattern near "Top 10"
    top10_match = re.search(r"([A-Z][a-zA-Z'\-]+(?:\s[A-Z][a-zA-Z'\-]+)?)'s Top 10", body_text)
    if top10_match:
        guest_name = top10_match.group(1)

    # --- Recommendations: find every ShopMy link on the page ---
    all_links = soup.find_all("a", href=True)
    shopmy_links = [a for a in all_links if "shopmy" in a["href"].lower()]

    rows = []
    for i, link in enumerate(shopmy_links, start=1):
        product_name = link.get_text(strip=True)
        product_link = link["href"]

        # Walk up to the wrapper span, then find the sibling <p> for the description
        parent_span = link.find_parent("span", class_="hxnnnr0")
        description = ""
        if parent_span:
            # The description span is usually in the next <p> sibling
            next_p = parent_span.find_next("p")
            if next_p:
                desc_span = next_p.find("span", class_="hxnnnr0")
                if desc_span:
                    description = desc_span.get_text(strip=True)

        rows.append({
            "row_id": i,
            "guest_name": guest_name,
            "guest_role": guest_role,
            "episode_date": date,
            "product_name": product_name,
            "product_link": product_link,
            "link_type": "ShopMy",
            "link_status": "Active",
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
