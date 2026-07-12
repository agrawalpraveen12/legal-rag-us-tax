import requests
import os
import time

API_KEY = "zRBs7U1dTTco8kRqzzUVSm8ZoflCdgl8JOHVDJeH"

MISSING_SECTIONS = [
    ("67",   "USCODE-2024-title26-subtitleA-chap1-subchapB-partI-sec67"),
    ("68",   "USCODE-2024-title26-subtitleA-chap1-subchapB-partI-sec68"),
    ("132",  "USCODE-2024-title26-subtitleA-chap1-subchapB-partIII-sec132"),
    ("151",  "USCODE-2024-title26-subtitleA-chap1-subchapB-partV-sec151"),
    ("199A", "USCODE-2024-title26-subtitleA-chap1-subchapB-partVI-sec199A"),
    ("265",  "USCODE-2024-title26-subtitleA-chap1-subchapB-partIX-sec265"),
]

BASE_URL = "https://www.govinfo.gov/content/pkg/USCODE-2024-title26/pdf/{granule}.pdf"
OUTPUT_DIR = "data/raw/acts"
os.makedirs(OUTPUT_DIR, exist_ok=True)

saved = 0
for section, granule in MISSING_SECTIONS:
    url = BASE_URL.format(granule=granule)
    out_path = os.path.join(OUTPUT_DIR, f"act_sec{section}.pdf")

    if os.path.exists(out_path):
        print(f"  SKIP §{section} — already exists")
        continue

    print(f"  Downloading §{section}...", end=" ", flush=True)
    resp = requests.get(url, params={"api_key": API_KEY}, timeout=30)

    if resp.status_code == 200 and resp.content[:4] == b"%PDF":
        with open(out_path, "wb") as f:
            f.write(resp.content)
        print(f"SAVED ({len(resp.content) // 1024} KB)")
        saved += 1
    else:
        print(f"FAILED (HTTP {resp.status_code}) — {url}")

    time.sleep(1)

print(f"\nDone. Saved {saved}/{len(MISSING_SECTIONS)} missing files.")
total = len([f for f in os.listdir(OUTPUT_DIR) if f.endswith(".pdf")])
print(f"Total PDFs in {OUTPUT_DIR}: {total}")
