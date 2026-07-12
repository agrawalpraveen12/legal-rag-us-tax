import sys
import requests
import os
import time
import csv
import re

# Force UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API_TOKEN = "755ecc684849021f8273300142ec79eaba55765e"
BASE      = "https://www.courtlistener.com/api/rest/v4"
OUT_DIR   = "data/raw/judgments"
SLEEP     = 12

os.makedirs(OUT_DIR, exist_ok=True)

HEADERS = {
    "Authorization": f"Token {API_TOKEN}",
    "User-Agent": "data-collection-research/1.0",
}

CASES = [
    (1,  "Commissioner v Glenshaw Glass",          "scotus", "IRC §61"),
    (2,  "Old Colony Trust Co v Commissioner",     "scotus", "IRC §61"),
    (3,  "Cesarini v United States",               "ca6",    "IRC §61"),
    (4,  "Welch v Helvering",                      "scotus", "IRC §162"),
    (5,  "Commissioner v Tellier",                 "scotus", "IRC §162"),
    (6,  "INDOPCO v Commissioner",                 "scotus", "IRC §162"),
    (7,  "Bob Jones University v United States",   "scotus", "IRC §501"),
    (8,  "Gregory v Helvering",                    "ca2",    "IRC §368"),
    (9,  "Cottage Savings Association v Commissioner", "scotus", "IRC §1001"),
    (10, "Starker v United States",                "ca9",    "IRC §1031"),
    (11, "Cheek v United States",                  "scotus", "IRC §7201"),
    (12, "United States v Kirby Lumber",           "scotus", "IRC §61"),
    (13, "Farid-Es-Sultaneh v Commissioner",       "ca2",    "IRC §102"),
    (14, "Commissioner v Duberstein",              "scotus", "IRC §102"),
    (15, "Crane v Commissioner",                   "scotus", "IRC §1001"),
    (16, "Commissioner v Tufts",                   "scotus", "IRC §1001"),
    (17, "Arrowsmith v Commissioner",              "scotus", "IRC §1221"),
    (18, "Corn Products Refining v Commissioner",  "scotus", "IRC §1221"),
    (19, "Arkansas Best Corporation v Commissioner","scotus", "IRC §1221"),
    (20, "Grodt McKay Realty v Commissioner",      "tax",    "IRC §1031"),
    (21, "Estate of Franklin v Commissioner",      "ca9",    "IRC §167"),
    (22, "United States v Gilmore",                "scotus", "IRC §165"),
    (23, "Commissioner v Flowers",                 "scotus", "IRC §162"),
    (24, "Hernandez v Commissioner",               "scotus", "IRC §170"),
    (25, "Benaglia v Commissioner",                "bta",    "IRC §61"),
    (26, "Moller v United States",                 "uscfc",  "IRC §183"),
    (27, "Textron Inc v United States",            "ca1",    "IRC §6662"),
    (28, "Helvering v Bruun",                      "scotus", "IRC §61"),
    (29, "Davis v United States",                  "scotus", "IRC §170"),
    (30, "Commissioner v Idaho Power",             "scotus", "IRC §263"),
]


def slugify(name):
    s = name.lower()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    s = re.sub(r"\s+", "_", s.strip())
    return s


def cl_get(url, params=None):
    """GET with auth; sleeps SLEEP seconds afterwards."""
    r = requests.get(url, headers=HEADERS, params=params, timeout=40)
    time.sleep(SLEEP)
    return r


def fetch_pdf(url):
    """Download a PDF binary; no auth header needed for storage CDN."""
    r = requests.get(url, timeout=60)
    time.sleep(SLEEP)
    return r


manifest = []
failed   = []

for idx, case_name, court, statute in CASES:
    slug   = slugify(case_name)
    prefix = f"judgment_{idx:02d}_{slug}"
    print(f"\n[{idx:02d}/30] {case_name}")

    # ── Step 1: search ────────────────────────────────────────────────────────
    r = cl_get(f"{BASE}/search/", params={"q": f'"{case_name}"', "type": "o"})
    if r.status_code != 200:
        msg = f"search HTTP {r.status_code}"
        print(f"  FAIL – {msg}")
        failed.append(f"{idx:02d}|{case_name}|{msg}")
        continue

    results = r.json().get("results", [])
    if not results:
        print(f"  FAIL – not found in search")
        failed.append(f"{idx:02d}|{case_name}|not_found")
        continue

    first      = results[0]
    cluster_id = first.get("cluster_id") or first.get("id")
    print(f"  cluster_id = {cluster_id}")

    # ── Step 2: fetch cluster ─────────────────────────────────────────────────
    r2 = cl_get(f"{BASE}/clusters/{cluster_id}/")
    if r2.status_code != 200:
        msg = f"cluster HTTP {r2.status_code}"
        print(f"  FAIL – {msg}")
        failed.append(f"{idx:02d}|{case_name}|{msg}")
        continue

    cluster      = r2.json()
    api_name     = cluster.get("case_name", case_name)
    api_court    = cluster.get("court_id", court)
    cl_page_url  = f"https://www.courtlistener.com/opinion/{cluster_id}/{slug}/"

    # cluster exposes sub_opinions as a list of URLs
    sub_opinion_urls = cluster.get("sub_opinions", [])

    # ── Step 3: fetch first opinion for content ───────────────────────────────
    if not sub_opinion_urls:
        print(f"  FAIL – no sub_opinions in cluster")
        failed.append(f"{idx:02d}|{case_name}|no_sub_opinions")
        continue

    opinion_url = sub_opinion_urls[0]
    r3 = cl_get(opinion_url)
    if r3.status_code != 200:
        msg = f"opinion HTTP {r3.status_code}"
        print(f"  FAIL – {msg}")
        failed.append(f"{idx:02d}|{case_name}|{msg}")
        continue

    opinion      = r3.json()
    pdf_rel      = opinion.get("filepath_pdf_harvard") or ""
    plain_text   = opinion.get("plain_text") or ""
    html_text    = opinion.get("html_with_citations") or opinion.get("html_lawbox") or ""

    # ── Step 4: save ──────────────────────────────────────────────────────────
    saved     = False
    file_type = None
    file_name = None

    if pdf_rel:
        # Build absolute URL for the Harvard PDF
        if pdf_rel.startswith("http"):
            pdf_url = pdf_rel
        else:
            pdf_url = f"https://storage.courtlistener.com/{pdf_rel.lstrip('/')}"

        print(f"  Downloading PDF → {pdf_url}")
        rp = fetch_pdf(pdf_url)

        if rp.status_code == 200 and rp.content[:4] == b"%PDF":
            file_name = f"{prefix}.pdf"
            out_path  = os.path.join(OUT_DIR, file_name)
            with open(out_path, "wb") as f:
                f.write(rp.content)
            print(f"  SAVED PDF ({len(rp.content) // 1024} KB) → {file_name}")
            file_type = "pdf"
            saved     = True
        else:
            print(f"  PDF fetch failed (HTTP {rp.status_code}), falling back to text")

    if not saved:
        content = plain_text or re.sub(r"<[^>]+>", " ", html_text)
        if content.strip():
            file_name = f"{prefix}.txt"
            out_path  = os.path.join(OUT_DIR, file_name)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"  SAVED TXT ({len(content):,} chars) → {file_name}")
            file_type = "txt"
            saved     = True

    if not saved:
        print(f"  FAIL – no PDF or text content")
        failed.append(f"{idx:02d}|{case_name}|no_content")
        continue

    manifest.append({
        "id":             cluster_id,
        "file_name":      file_name,
        "case_name":      api_name,
        "court":          api_court,
        "paired_statute": statute,
        "file_type":      file_type,
        "url":            cl_page_url,
    })

# ── Write manifest ─────────────────────────────────────────────────────────────
manifest_path = os.path.join(OUT_DIR, "judgments_manifest.csv")
with open(manifest_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=["id", "file_name", "case_name", "court",
                    "paired_statute", "file_type", "url"],
    )
    writer.writeheader()
    writer.writerows(manifest)
print(f"\nManifest saved → {manifest_path}  ({len(manifest)} rows)")

# ── Write failed ───────────────────────────────────────────────────────────────
if failed:
    failed_path = os.path.join(OUT_DIR, "failed.txt")
    with open(failed_path, "w", encoding="utf-8") as f:
        f.write("\n".join(failed) + "\n")
    print(f"Failed cases  → {failed_path}  ({len(failed)} entries)")
else:
    print("No failures.")

# ── Summary ────────────────────────────────────────────────────────────────────
judgment_files = [
    fn for fn in os.listdir(OUT_DIR)
    if fn.startswith("judgment_") and not fn.endswith(".csv")
]
print(f"\nTotal judgment files in {OUT_DIR}: {len(judgment_files)}")
print("Done.")
