"""One-shot: discover Mudah region codes by inspecting each state's listing page __NEXT_DATA__.initialQuery."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import time
import random
import cloudscraper
from bs4 import BeautifulSoup

STATES = [
    "johor", "kedah", "kelantan", "kuala-lumpur", "labuan",
    "melaka", "negeri-sembilan", "pahang", "penang", "perak",
    "perlis", "putrajaya", "sabah", "sarawak", "selangor", "terengganu",
]

s = cloudscraper.create_scraper(
    browser={"browser": "firefox", "platform": "windows", "mobile": False}, delay=10
)

result = {}
for state in STATES:
    url = f"https://www.mudah.my/{state}/properties-for-rent?o=1"
    for attempt in range(3):
        try:
            r = s.get(url, timeout=30)
        except Exception as e:
            print(f"  {state} attempt {attempt+1}: ERROR {e}")
            time.sleep(5)
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        script = soup.find("script", id="__NEXT_DATA__")
        if script:
            break
        # Cloudflare block — back off and retry
        backoff = 5 + attempt * 10
        print(f"  {state} attempt {attempt+1}: NO __NEXT_DATA__ (status={r.status_code}), backing off {backoff}s")
        time.sleep(backoff)
    if not script:
        print(f"  {state}: FAILED after retries")
        continue
    data = json.loads(script.text)
    iq = data.get("props", {}).get("pageProps", {}).get("initialQuery", {})
    region_id = iq.get("region")
    print(f"  {state}: region={region_id}")
    if region_id:
        result[state] = region_id
    # Polite delay between successful states
    time.sleep(random.uniform(3, 6))

print("\n# Paste into config.py:")
print("REGION_CODES = {")
for k, v in sorted(result.items()):
    print(f'    "{k}": "{v}",')
print("}")
