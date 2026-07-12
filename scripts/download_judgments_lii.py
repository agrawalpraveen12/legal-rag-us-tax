import sys, requests, os, time
from bs4 import BeautifulSoup

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

headers = {"User-Agent": "Mozilla/5.0 Legal Research Project"}
OUTPUT_DIR = "data/raw/judgments"

cases = [
    {
        "filename": "judgment_09_cottage_savings_association_v_commissioner.txt",
        "url": "https://supreme.justia.com/cases/federal/us/499/554/",
        "source": "justia"
    },
    {
        "filename": "judgment_11_cheek_v_united_states.txt",
        "url": "https://supreme.justia.com/cases/federal/us/498/192/",
        "source": "justia"
    },
    {
        "filename": "judgment_12_united_states_v_kirby_lumber.txt",
        "url": "https://supreme.justia.com/cases/federal/us/284/1/",
        "source": "justia"
    },
    {
        "filename": "judgment_13_faridessultaneh_v_commissioner.txt",
        "url": "https://law.justia.com/cases/federal/appellate-courts/F2/160/812/1547456/",
        "source": "justia"
    },
    {
        "filename": "judgment_15_crane_v_commissioner.txt",
        "url": "https://supreme.justia.com/cases/federal/us/331/1/",
        "source": "justia"
    },
    {
        "filename": "judgment_16_commissioner_v_tufts.txt",
        "url": "https://supreme.justia.com/cases/federal/us/461/300/",
        "source": "justia"
    },
    {
        "filename": "judgment_19_arkansas_best_corporation_v_commissioner.txt",
        "url": "https://supreme.justia.com/cases/federal/us/485/212/",
        "source": "justia"
    },
    {
        "filename": "judgment_30_commissioner_v_idaho_power.txt",
        "url": "https://supreme.justia.com/cases/federal/us/418/1/",
        "source": "justia"
    },
]

cornell_urls = {
    "judgment_09": "https://www.law.cornell.edu/supremecourt/text/499/554",
    "judgment_11": "https://www.law.cornell.edu/supremecourt/text/498/192",
    "judgment_12": "https://www.law.cornell.edu/supremecourt/text/284/1",
    "judgment_15": "https://www.law.cornell.edu/supremecourt/text/331/1",
    "judgment_16": "https://www.law.cornell.edu/supremecourt/text/461/300",
    "judgment_19": "https://www.law.cornell.edu/supremecourt/text/485/212",
    "judgment_30": "https://www.law.cornell.edu/supremecourt/text/418/1",
}

def extract_justia(url):
    r = requests.get(url, headers=headers, timeout=30)
    if r.status_code != 200:
        print(f"    Justia HTTP {r.status_code}")
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    opinion = (soup.find("div", {"class": "tab-content"}) or
               soup.find("div", {"id": "opinion"}) or
               soup.find("div", {"class": "opinion"}) or
               soup.find("main") or
               soup.find("article") or
               soup.body)
    if opinion:
        text = opinion.get_text(separator="\n", strip=True)
        return text if len(text) > 1000 else None
    return None

def extract_cornell(url):
    r = requests.get(url, headers=headers, timeout=30)
    if r.status_code != 200:
        print(f"    Cornell HTTP {r.status_code}")
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    content = (soup.find("div", {"id": "opinion"}) or
               soup.find("div", {"class": "opinion"}) or
               soup.find("main"))
    if content:
        text = content.get_text(separator="\n", strip=True)
        return text if len(text) > 1000 else None
    return None

for case in cases:
    path = os.path.join(OUTPUT_DIR, case["filename"])
    key  = case["filename"][:11]
    print(f"\n[{case['filename']}]")

    if os.path.exists(path):
        os.remove(path)
        print(f"  Deleted existing file")

    saved = False

    # Try Justia first
    print(f"  Trying Justia: {case['url']}")
    text = extract_justia(case["url"])
    if text and len(text) > 1000:
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"Source: {case['url']}\n\n{text}")
        print(f"  SAVED ({os.path.getsize(path)//1024}KB) from Justia")
        saved = True

    # Cornell LII fallback
    if not saved and key in cornell_urls:
        print(f"  Trying Cornell LII: {cornell_urls[key]}")
        text2 = extract_cornell(cornell_urls[key])
        if text2 and len(text2) > 1000:
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"Source: {cornell_urls[key]}\n\n{text2}")
            print(f"  SAVED ({os.path.getsize(path)//1024}KB) from Cornell LII")
            saved = True

    if not saved:
        print(f"  FAILED — both sources returned no usable text")

    time.sleep(5)

# Final check
print("\n=== FINAL STATUS ===")
txt_files = [f for f in os.listdir(OUTPUT_DIR) if f.endswith(".txt") and f != "failed.txt"]
good = [f for f in txt_files if os.path.getsize(os.path.join(OUTPUT_DIR, f)) > 5000]
bad  = [f for f in txt_files if os.path.getsize(os.path.join(OUTPUT_DIR, f)) <= 5000]
print(f"Good files (>5KB): {len(good)}/30")
if bad:
    print(f"Still bad (<= 5KB): {bad}")
