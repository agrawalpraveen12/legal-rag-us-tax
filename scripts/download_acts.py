import requests
import os
import time

API_KEY = "zRBs7U1dTTco8kRqzzUVSm8ZoflCdgl8JOHVDJeH"  # paste your api.data.gov key

# Each entry: (section_number, granule_id_path)
# Granule IDs confirmed from GovInfo search results
SECTIONS = [
    ("61",   "USCODE-2024-title26-subtitleA-chap1-subchapB-partI-sec61"),
    ("62",   "USCODE-2024-title26-subtitleA-chap1-subchapB-partI-sec62"),
    ("63",   "USCODE-2024-title26-subtitleA-chap1-subchapB-partI-sec63"),
    ("101",  "USCODE-2024-title26-subtitleA-chap1-subchapB-partIII-sec101"),
    ("102",  "USCODE-2024-title26-subtitleA-chap1-subchapB-partIII-sec102"),
    ("121",  "USCODE-2024-title26-subtitleA-chap1-subchapB-partIII-sec121"),
    ("162",  "USCODE-2024-title26-subtitleA-chap1-subchapB-partVI-sec162"),
    ("163",  "USCODE-2024-title26-subtitleA-chap1-subchapB-partVI-sec163"),
    ("165",  "USCODE-2024-title26-subtitleA-chap1-subchapB-partVI-sec165"),
    ("167",  "USCODE-2024-title26-subtitleA-chap1-subchapB-partVI-sec167"),
    ("170",  "USCODE-2024-title26-subtitleA-chap1-subchapB-partVI-sec170"),
    ("183",  "USCODE-2024-title26-subtitleA-chap1-subchapB-partVI-sec183"),
    ("212",  "USCODE-2024-title26-subtitleA-chap1-subchapB-partVI-sec212"),
    ("263",  "USCODE-2024-title26-subtitleA-chap1-subchapB-partIX-sec263"),
    ("351",  "USCODE-2024-title26-subtitleA-chap1-subchapC-partIII-sec351"),
    ("368",  "USCODE-2024-title26-subtitleA-chap1-subchapC-partIII-sec368"),
    ("401",  "USCODE-2024-title26-subtitleA-chap1-subchapD-partI-sec401"),
    ("408",  "USCODE-2024-title26-subtitleA-chap1-subchapD-partI-sec408"),
    ("501",  "USCODE-2024-title26-subtitleA-chap1-subchapF-partI-sec501"),
    ("1001", "USCODE-2024-title26-subtitleA-chap1-subchapO-partI-sec1001"),
    ("1031", "USCODE-2024-title26-subtitleA-chap1-subchapO-partIII-sec1031"),
    ("1221", "USCODE-2024-title26-subtitleA-chap1-subchapP-partIV-sec1221"),
    ("6662", "USCODE-2024-title26-subtitleF-chap68-subchapA-partII-sec6662"),
    ("7201", "USCODE-2024-title26-subtitleF-chap75-subchapA-partI-sec7201"),
]

BASE_URL = "https://www.govinfo.gov/content/pkg/USCODE-2024-title26/pdf/{granule}.pdf"
OUTPUT_DIR = "data/raw/acts"
os.makedirs(OUTPUT_DIR, exist_ok=True)

for section, granule in SECTIONS:
    url = BASE_URL.format(granule=granule)
    out_path = os.path.join(OUTPUT_DIR, f"act_sec{section}.pdf")
    
    if os.path.exists(out_path):
        print(f"  SKIP §{section} — already exists")
        continue
    
    print(f"  Downloading §{section}...", end=" ")
    resp = requests.get(url, timeout=30)
    
    if resp.status_code == 200:
        with open(out_path, "wb") as f:
            f.write(resp.content)
        print(f"SAVED ({len(resp.content)//1024}KB)")
    else:
        print(f"FAILED (HTTP {resp.status_code}) — URL: {url}")
    
    time.sleep(1)  # be polite

print("\nDone. Check data/raw/acts/")