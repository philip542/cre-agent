import anthropic
import requests
from bs4 import BeautifulSoup
import csv
import json
import os
from datetime import datetime
import time

# ---- SETTINGS ----
API_KEY = os.environ.get("ANTHROPIC_API_KEY")
OUTPUT_FILE = "cre_transactions.csv"
SEEN_FILE = "seen_urls.txt"
MAX_PAGES = 1  # Weekly run — page 1 only (change to 47 for full backfill)
# ------------------

client = anthropic.Anthropic(api_key=API_KEY)

def load_seen_urls():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(f.read().splitlines())
    return set()

def save_seen_urls(seen):
    with open(SEEN_FILE, "w") as f:
        f.write("\n".join(seen))

def get_article_links(page=1):
    url = f"https://www.cremediaeurope.com/news/?page={page}" if page > 1 else "https://www.cremediaeurope.com/news/"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/news/" in href and "~" in href:
                full_url = "https://www.cremediaeurope.com" + href
                if full_url not in links:
                    links.append(full_url)
        return links
    except:
        return []

def get_article_text(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers, timeout=10)
    soup = BeautifulSoup(response.text, "html.parser")
    return " ".join([p.get_text() for p in soup.find_all("p")])

def extract_transaction(article_text):
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{"role": "user", "content": f"""Read this real estate article and return ONLY a JSON object, no other text.

If the article describes a real estate transaction return:
{{
  "is_transaction": true,
  "buyer_name": "buyer name or null",
  "buyer_country": "buyer country or null",
  "asset_class": "Offices/Logistics/Retail/Residential/Hotels/Mixed-use or null",
  "asset_location": "city, country or null",
  "price": "price as stated or null",
  "strategy": "Core/Core-plus/Value-add/Opportunistic or null",
  "deal_type": "Acquisition/Disposal/Refinancing/JV/Development or null"
}}

If NOT a transaction (research, people news, opinion) return:
{{"is_transaction": false}}

Article: {article_text[:2000]}"""}]
    )
    raw = message.content[0].text.strip()
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        return {"is_transaction": False}
    return json.loads(raw[start:end])

def run():
    seen = load_seen_urls()
    total_found = 0

    file_exists = os.path.exists(OUTPUT_FILE)
    fields = ["buyer_name", "buyer_country", "asset_class", "asset_location",
              "price", "strategy", "deal_type", "source_url", "date_scraped"]

    output = open(OUTPUT_FILE, "a" if file_exists else "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    if not file_exists:
        writer.writeheader()

    print(f"🚀 Starting weekly run — {MAX_PAGES} page(s)")
    print(f"📋 Already seen: {len(seen)} URLs\n")

    for page in range(1, MAX_PAGES + 1):
        print(f"\n📄 PAGE {page}/{MAX_PAGES}")
        links = get_article_links(page)
        new_links = [l for l in links if l not in seen]
        print(f"   Found {len(links)} articles, {len(new_links)} new")

        for i, url in enumerate(new_links):
            slug = url.split("~")[0].split("/")[-1][:45]
            print(f"   🔍 {i+1}/{len(new_links)}: {slug}")
            try:
                text = get_article_text(url)
                data = extract_transaction(text)
                seen.add(url)

                if data.get("is_transaction"):
                    data["source_url"] = url
                    data["date_scraped"] = datetime.today().strftime("%Y-%m-%d")
                    writer.writerow(data)
                    output.flush()
                    total_found += 1
                    print(f"      ✅ {data.get('buyer_name','?')} | {data.get('asset_class','?')} | {data.get('asset_location','?')} | {data.get('price','?')}")
                else:
                    print(f"      ⏭ Not a transaction")

                time.sleep(0.3)

            except Exception as e:
                print(f"      ⚠️ Error: {e}")

        save_seen_urls(seen)

    output.close()
    print(f"\n🎉 Done! {total_found} new transactions added to {OUTPUT_FILE}")

run()
