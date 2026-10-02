import os
import re
import hashlib
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


# ---------- GUEST NAME EXTRACTION ----------
def extract_guest_name(soup, body_text, title):
    """
    Extract guest name using a priority chain:
    1. og:image filename (HSR_DrSashaHamdani_2_.png)
    2. og:description / twitter:description "with X" pattern
    3. twitter:title / og:title "with X" pattern
    4. Intro paragraph patterns
    5. "X's Top 10" heading
    """
    # --- Priority 1: og:image filename ---
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        url = og_image["content"]
        filename = url.split("/")[-1].split("?")[0]

        raw = re.sub(r"\.(png|jpg|jpeg)$", "", filename, flags=re.IGNORECASE)
        raw = re.sub(r"^[A-Z]{2,5}_", "", raw)
        raw = re.sub(r"_\d+_?$", "", raw)
        raw = raw.rstrip("_")

        raw = raw.replace("_", " ")
        spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", raw)
        spaced = re.sub(r"\s+", " ", spaced).strip()
        spaced = re.sub(r"(\w)\d+$", r"\1", spaced)
        spaced = re.sub(r"^(Dr|Mr|Mrs|Ms)\s", r"\1. ", spaced)

        if spaced.lower() not in ("default", "cover", "image") and len(spaced.split()) >= 2:
            return spaced

    # --- Priority 2: og:description / twitter:description ---
    for meta_prop in ("og:description", "twitter:description"):
        tag = soup.find("meta", property=meta_prop) or soup.find(
            "meta", attrs={"name": meta_prop}
        )
        if tag and tag.get("content"):
            text = tag["content"]
            m = re.search(
                r"\bwith\s+((?:Dr\.?|Mr\.?|Mrs\.?|Ms\.?)?\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\s*$",
                text,
            )
            if m:
                return m.group(1).strip()

    # --- Priority 3: twitter:title / og:title ---
    for meta_prop in ("twitter:title", "og:title"):
        tag = soup.find("meta", attrs={"name": meta_prop}) or soup.find(
            "meta", property=meta_prop
        )
        if tag and tag.get("content"):
            text = tag["content"]
            m = re.search(
                r"\bwith\s+((?:Dr\.?|Mr\.?|Mrs\.?|Ms\.?)?\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\s*$",
                text,
            )
            if m:
                return m.group(1).strip()

    # --- Priority 4: Intro paragraph patterns ---
    intro_patterns = [
        r"sitting down with\s+([A-Z][a-zA-Z'\-\.]+(?:\s+[A-Z][a-zA-Z'\-\.]+){0,3})",
        r"talking to\s+([A-Z][a-zA-Z'\-\.]+(?:\s+[A-Z][a-zA-Z'\-\.]+){0,3})",
        r"my friend,\s+([A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+){0,3})",
    ]
    for pattern in intro_patterns:
        m = re.search(pattern, body_text)
        if m:
            candidate = m.group(1).strip()
            if len(candidate.split()) >= 2:
                return candidate

    # --- Priority 5: "X's Top 10" heading ---
    for h in soup.find_all(["h1", "h2", "h3", "h4"]):
        text = h.get_text(strip=True)
        if "top 10" in text.lower():
            m = re.match(r"^(.+?)'?s?\s+Top 10", text, re.IGNORECASE)
            if m:
                candidate = m.group(1).strip()
                if candidate.lower() not in ("maggie", "maggie sellers reum", "host"):
                    return candidate

    return ""


# ---------- PARSE ----------
def parse_episode(html, url):
    soup = BeautifulSoup(html, "html.parser")
    body_text = soup.get_text(" ", strip=True)

    # --- Header metadata ---
    header_spans = soup.select("span._11r14xt1")
    title = header_spans[0].get_text(strip=True) if len(header_spans) > 0 else ""

    # --- Date: extract by pattern ---
    date = ""
    date_patterns = [
        r"\b\d{4}-\d{2}-\d{2}\b",
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}\b",
        r"\b\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{4}\b",
    ]
    for span in header_spans:
        text = span.get_text(strip=True)
        for pattern in date_patterns:
            m = re.search(pattern, text)
            if m:
                date = m.group(0)
                break
        if date:
            break

    if not date:
        time_tag = soup.find("time")
        if time_tag:
            date = time_tag.get_text(strip=True) or time_tag.get("datetime", "")

    if not date:
        print(f"  WARNING: no date found on {url}")

    # --- Guest name ---
    guest_name = extract_guest_name(soup, body_text, title)
    if not guest_name:
        print(f"  WARNING: could not extract guest name from {url}")

    # --- Find the guest's Top 10 heading ---
    top10_heading = None
    candidates = []
    for h in soup.find_all(["h1", "h2", "h3", "h4"]):
        text = h.get_text(strip=True)
        if "top 10" in text.lower():
            candidates.append(h)

    if guest_name:
        first_name = guest_name.split()[0].lower().rstrip(".")
        for h in candidates:
            if first_name in h.get_text(strip=True).lower():
                top10_heading = h
                break

    if top10_heading is None and candidates:
        top10_heading = candidates[0]

    if not top10_heading:
        print(f"  No 'Top 10' heading found on {url}")
        return []

    # --- Collect div.j6zgbu0 blocks between this heading and next h1/h2 ---
    target_blocks = []
    for elem in top10_heading.next_elements:
        name = getattr(elem, "name", None)
        if name in ["h1", "h2"]:
            break
        if name == "div" and "j6zgbu0" in elem.get("class", []):
            target_blocks.append(elem)

    # --- Parse each block (linked AND unlinked) ---
    rows = []
    for block in target_blocks:
        raw_text = block.get_text(" ", strip=True)
        raw_text = re.sub(r"\s+", " ", raw_text).strip()

        # Skip the section subtitle ("her top 10 to live a hot, smart, rich life")
        if "top 10 to live a" in raw_text.lower():
            continue

        # Skip blocks that don't start with a numbered item
        if not re.match(r"^\d{1,2}[\.\)]\s", raw_text):
            continue

        full_text = re.sub(r"^\d{1,2}[\.\)]?\s*", "", raw_text).strip()
        if not full_text:
            continue

        product_name = ""
        product_link = ""
        link_type = "None"
        link_status = "Placeholder"

        link = block.find("a", href=True)
        if link:
            product_name = link.get_text(strip=True)
            product_link = link["href"]
            link_status = "Active"
            if "shopmy" in product_link.lower():
                link_type = "ShopMy"
            elif "amzn" in product_link.lower():
                link_type = "Amazon"
            else:
                link_type = "Direct"
        else:
            product_name = re.split(
                r"\s+(?:is|are|gives|makes|means|helps|lets|keeps|has|have|because)\s+",
                full_text,
                maxsplit=1,
            )[0].strip()
            if len(product_name) > 60:
                product_name = product_name[:60].rsplit(" ", 1)[0] + "…"

        # Stable row_id based on the product name (not its position)
        row_id = int(hashlib.sha256(f"{url}#{product_name}".encode()).hexdigest()[:8], 16)

        rows.append({
            "row_id": row_id,
            "guest_name": guest_name,
            "guest_role": "Guest",
            "episode_date": date,
            "product_name": product_name,
            "product_link": product_link,
            "link_type": link_type,
            "link_status": link_status,
            "guest_description": full_text,
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
    result = turso_execute("SELECT DISTINCT source_url FROM recommendations")
    try:
        rows = result["results"][0]["response"]["result"]["rows"]
    except (KeyError, IndexError, TypeError) as e:
        print(f"  WARNING: unexpected Turso response shape: {e}")
        return set()

    urls = set()
    for row in rows:
        if not row:
            continue
        cell = row[0]
        if isinstance(cell, dict) and "value" in cell:
            urls.add(cell["value"])
        elif isinstance(cell, str):
            urls.add(cell)

    print(f"  Parsed {len(urls)} unique source_urls from Turso")
    return urls


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
