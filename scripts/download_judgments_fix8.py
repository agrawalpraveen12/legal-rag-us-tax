import sys, requests, os, time, io
import pypdf

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOKEN = "755ecc684849021f8273300142ec79eaba55765e"
HEADERS = {"Authorization": f"Token {TOKEN}"}
BASE    = "https://www.courtlistener.com/api/rest/v4"
OUTDIR  = "data/raw/judgments"
MIN_CHARS = 5000

cases = [
    ("judgment_09_cottage_savings_association_v_commissioner.txt", "Cottage Savings Association v Commissioner", "scotus", 1991),
    ("judgment_11_cheek_v_united_states.txt",                     "Cheek v United States",                    "scotus", 1991),
    ("judgment_12_united_states_v_kirby_lumber.txt",              "United States v Kirby Lumber",             "scotus", 1931),
    ("judgment_13_faridessultaneh_v_commissioner.txt",            "Farid-Es-Sultaneh v Commissioner",         "ca2",    1947),
    ("judgment_15_crane_v_commissioner.txt",                      "Crane v Commissioner",                     "scotus", 1947),
    ("judgment_16_commissioner_v_tufts.txt",                      "Commissioner v Tufts",                     "scotus", 1983),
    ("judgment_19_arkansas_best_corporation_v_commissioner.txt",  "Arkansas Best Corporation v Commissioner", "scotus", 1988),
    ("judgment_30_commissioner_v_idaho_power.txt",                "Commissioner v Idaho Power",               "scotus", 1974),
]

def get_opinion_text(opinion_id):
    r = requests.get(f"{BASE}/opinions/{opinion_id}/", headers=HEADERS, timeout=30)
    if r.status_code != 200:
        return ""
    d = r.json()
    return (d.get("plain_text")    or
            d.get("html_lawbox")   or
            d.get("html_columbia") or
            d.get("html")          or "")

def get_harvard_pdf_text(cluster_id):
    pdf_url = f"https://storage.courtlistener.com/harvard_pdf/{cluster_id}.pdf"
    r = requests.get(pdf_url, headers=HEADERS, timeout=60)
    if r.status_code != 200 or r.content[:4] != b"%PDF":
        return ""
    reader = pypdf.PdfReader(io.BytesIO(r.content))
    return "\n".join(p.extract_text() or "" for p in reader.pages)

def search_case(case_name, court, year):
    """Try multiple query strategies; return (cluster_id, opinion_id, case_name_found) or None."""
    queries = [
        f'"{case_name}"',
        case_name,
        " ".join(case_name.split()[:3]),
    ]
    for q in queries:
        for use_court in [True, False]:
            params = {"q": q, "type": "o", "order_by": "score desc", "page_size": 20}
            if use_court:
                params["court"] = court
            try:
                r = requests.get(f"{BASE}/search/", headers=HEADERS, params=params, timeout=30)
                if r.status_code == 429:
                    wait = int(r.headers.get("Retry-After", 120))
                    print(f"    429 — sleeping {wait}s")
                    time.sleep(wait + 5)
                    continue
                if r.status_code != 200:
                    continue
                results = r.json().get("results", [])
                # Filter by correct year
                year_results = [x for x in results
                                if str(year) in (x.get("dateFiled") or "")]
                pool = year_results if year_results else results
                if not pool:
                    continue
                best = max(pool, key=lambda x: x.get("citeCount", 0))
                ops  = best.get("opinions", [])
                if not ops:
                    continue
                opinion_id = ops[0]["id"]
                cluster_id = best.get("cluster_id")
                found_name = best.get("caseName", "")
                print(f"    hit: '{found_name}' filed={best.get('dateFiled','')} cites={best.get('citeCount',0)} op={opinion_id}")
                return cluster_id, opinion_id, found_name
            except Exception as e:
                print(f"    search error: {e}")
        time.sleep(3)
    return None

# ── Main loop ─────────────────────────────────────────────────────────────────
for filename, case_name, court, year in cases:
    path = os.path.join(OUTDIR, filename)
    print(f"\n[{filename}]  target={case_name} ({year})")

    # Delete wrong/stub file
    if os.path.exists(path):
        os.remove(path)
        print(f"  Deleted existing file")

    found = False
    result = search_case(case_name, court, year)

    if result:
        cluster_id, opinion_id, found_name = result
        text = get_opinion_text(opinion_id)
        time.sleep(3)

        if len(text) >= MIN_CHARS:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"  SAVED via opinion text  ({len(text)//1024}KB)  '{found_name}'")
            found = True
        else:
            print(f"  Opinion text too short ({len(text)} chars) — trying Harvard PDF")
            pdf_text = get_harvard_pdf_text(cluster_id)
            if len(pdf_text) >= MIN_CHARS:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(pdf_text)
                print(f"  SAVED via Harvard PDF  ({len(pdf_text)//1024}KB)  '{found_name}'")
                found = True
            else:
                print(f"  Harvard PDF also short ({len(pdf_text)} chars)")
    else:
        print(f"  No matching cluster found")

    if not found:
        print(f"  FAILED")
        with open(os.path.join(OUTDIR, "failed.txt"), "a", encoding="utf-8") as f:
            f.write(f"{filename}\n")

    print(f"  Sleeping 20s...")
    time.sleep(20)

# ── Summary ───────────────────────────────────────────────────────────────────
files = [f for f in os.listdir(OUTDIR) if f.endswith(".txt") and f != "failed.txt"]
good  = [f for f in files if os.path.getsize(os.path.join(OUTDIR, f)) >= MIN_CHARS]
print(f"\n=== DONE: {len(good)}/{len(files)} judgment files >= 5KB ===")
for f in sorted(files):
    kb = os.path.getsize(os.path.join(OUTDIR, f)) // 1024
    flag = "" if os.path.getsize(os.path.join(OUTDIR, f)) >= MIN_CHARS else "  *** SMALL"
    print(f"  {kb:>5}KB  {f}{flag}")
