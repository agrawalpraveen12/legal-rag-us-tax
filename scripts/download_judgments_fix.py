"""
Fix + complete judgment downloads.
- Skips files already > GOOD_BYTES (5 KB).
- Retries stubs/missing with 3-strategy search + citeCount ranking.
- 15-second sleep after every API call.
"""
import sys, requests, os, time, csv, re

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API_TOKEN = "755ecc684849021f8273300142ec79eaba55765e"
BASE      = "https://www.courtlistener.com/api/rest/v4"
OUT_DIR   = "data/raw/judgments"
SLEEP     = 15
MIN_CHARS = 500
GOOD_BYTES = 5120

os.makedirs(OUT_DIR, exist_ok=True)

HDR = {
    "Authorization": f"Token {API_TOKEN}",
    "User-Agent": "data-collection-research/1.0",
}

# (idx, display_name, court, statute, citation_query, keyword_query)
# citation_query  → most-precise; searched first
# keyword_query   → fallback; searched last
CASES = [
    ( 1, "Commissioner v Glenshaw Glass",             "scotus","IRC §61",
         "Commissioner v Glenshaw Glass 348 US 426",  "Glenshaw Glass gross income treasure trove"),
    ( 2, "Old Colony Trust Co v Commissioner",        "scotus","IRC §61",
         "Old Colony Trust Co v Commissioner 279 US 716","Old Colony Trust employer tax payment"),
    ( 3, "Cesarini v United States",                  "ca6",  "IRC §61",
         "Cesarini v United States 296 F Supp 3",     "Cesarini found money piano gross income"),
    ( 4, "Welch v Helvering",                         "scotus","IRC §162",
         "Welch v Helvering 290 US 111",              "Welch Helvering ordinary necessary business expense"),
    ( 5, "Commissioner v Tellier",                    "scotus","IRC §162",
         "Commissioner v Tellier 383 US 687",         "Tellier legal fees criminal defense deduction"),
    ( 6, "INDOPCO v Commissioner",                    "scotus","IRC §162",
         "INDOPCO v Commissioner 503 US 79",          "INDOPCO capitalization acquisition future benefit"),
    ( 7, "Bob Jones University v United States",      "scotus","IRC §501",
         "Bob Jones University v United States 461 US 574","Bob Jones University tax exempt racial discrimination"),
    ( 8, "Gregory v Helvering",                       "scotus","IRC §368",
         "Gregory v Helvering 293 US 465",            "Gregory Helvering corporate reorganization sham"),
    ( 9, "Cottage Savings Association v Commissioner","scotus","IRC §1001",
         "Cottage Savings Association v Commissioner 499 US 554","Cottage Savings realization exchange materially different"),
    (10, "Starker v United States",                   "ca9",  "IRC §1031",
         "Starker v United States 602 F2d 1341",      "Starker deferred like kind exchange 1031"),
    (11, "Cheek v United States",                     "scotus","IRC §7201",
         "Cheek v United States 498 US 192",          "Cheek willfulness tax evasion good faith belief"),
    (12, "United States v Kirby Lumber",              "scotus","IRC §61",
         "United States v Kirby Lumber 284 US 1",     "Kirby Lumber debt discharge cancellation income"),
    (13, "Farid-Es-Sultaneh v Commissioner",          "ca2",  "IRC §102",
         "Farid-Es-Sultaneh v Commissioner 160 F2d 812","Farid Sultaneh prenuptial agreement basis gift consideration"),
    (14, "Commissioner v Duberstein",                 "scotus","IRC §102",
         "Commissioner v Duberstein 363 US 278",      "Duberstein gift income dominant motive"),
    (15, "Crane v Commissioner",                      "scotus","IRC §1001",
         "Crane v Commissioner 331 US 1",             "Crane encumbered property basis mortgage amount realized"),
    (16, "Commissioner v Tufts",                      "scotus","IRC §1001",
         "Commissioner v Tufts 461 US 300",           "Tufts nonrecourse mortgage exceeds fair market value"),
    (17, "Arrowsmith v Commissioner",                 "scotus","IRC §1221",
         "Arrowsmith v Commissioner 344 US 6",        "Arrowsmith related transaction capital loss character"),
    (18, "Corn Products Refining v Commissioner",     "scotus","IRC §1221",
         "Corn Products Refining v Commissioner 350 US 46","Corn Products futures ordinary asset integral business"),
    (19, "Arkansas Best Corporation v Commissioner",  "scotus","IRC §1221",
         "Arkansas Best Corporation v Commissioner 485 US 212","Arkansas Best stock capital asset predominant purpose"),
    (20, "Grodt McKay Realty v Commissioner",         "tax",  "IRC §1031",
         "Grodt McKay Realty v Commissioner 77 TC 1221","Grodt McKay like kind exchange beneficial ownership"),
    (21, "Estate of Franklin v Commissioner",         "ca9",  "IRC §167",
         "Estate of Franklin v Commissioner 544 F2d 1045","Estate Franklin nonrecourse depreciation tax shelter"),
    (22, "United States v Gilmore",                   "scotus","IRC §165",
         "United States v Gilmore 372 US 39",         "Gilmore divorce legal expenses origin of claim"),
    (23, "Commissioner v Flowers",                    "scotus","IRC §162",
         "Commissioner v Flowers 326 US 465",         "Flowers travel expense away from home tax home"),
    (24, "Hernandez v Commissioner",                  "scotus","IRC §170",
         "Hernandez v Commissioner 490 US 680",       "Hernandez charitable deduction quid pro quo Scientology"),
    (25, "Benaglia v Commissioner",                   "bta",  "IRC §61",
         "Benaglia v Commissioner 36 BTA 838",        "Benaglia meals lodging hotel manager exclusion"),
    (26, "Moller v United States",                    "uscfc","IRC §183",
         "Moller v United States 721 F2d 810",        "Moller hobby loss profit motive activity"),
    (27, "Textron Inc v United States",               "ca1",  "IRC §6662",
         "Textron Inc v United States 577 F3d 21",    "Textron work product privilege tax accrual reserves"),
    (28, "Helvering v Bruun",                         "scotus","IRC §61",
         "Helvering v Bruun 309 US 461",              "Bruun lease forfeiture improvement realization income"),
    (29, "Davis v United States",                     "scotus","IRC §170",
         "Davis v United States 495 US 472",          "Davis gift appreciated stock charitable deduction"),
    (30, "Commissioner v Idaho Power",                "scotus","IRC §263",
         "Commissioner v Idaho Power 418 US 1",       "Idaho Power capital expenditure self-constructed asset"),
]


def slugify(name):
    s = name.lower()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    s = re.sub(r"\s+", "_", s.strip())
    return s


def cl_get(url, params=None):
    r = requests.get(url, headers=HDR, params=params, timeout=40)
    time.sleep(SLEEP)
    return r


def fetch_pdf_url(url):
    r = requests.get(url, timeout=90)
    time.sleep(SLEEP)
    return r


def best_text(opinion: dict) -> str:
    """Return best available text from an opinion record."""
    for field in ("plain_text", "html_with_citations", "html_lawbox", "html_anon_2020"):
        val = opinion.get(field) or ""
        if len(val.strip()) >= MIN_CHARS:
            return val
    return ""


def strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


def search_and_fetch(query: str, label: str):
    """
    Search CL, collect results sorted by citeCount, try each until we get
    an opinion with enough content. Returns (cluster_id, court_id, file_ext, content)
    or None if nothing usable found.
    """
    print(f"    SEARCH: {query!r}")
    r = cl_get(f"{BASE}/search/", params={"q": query, "type": "o", "order_by": "citeCount desc"})
    if r.status_code != 200:
        print(f"    search HTTP {r.status_code}")
        return None

    results = r.json().get("results", [])
    if not results:
        print(f"    no results")
        return None

    # Sort client-side too (API may not honour order_by for all fields)
    results.sort(key=lambda x: x.get("citeCount", 0), reverse=True)
    print(f"    {len(results)} hits; top citeCount = {results[0].get('citeCount', '?')}")

    for res in results[:5]:                      # inspect top 5
        cluster_id = res.get("cluster_id") or res.get("id")
        if not cluster_id:
            continue

        # Fetch cluster
        r2 = cl_get(f"{BASE}/clusters/{cluster_id}/")
        if r2.status_code != 200:
            continue
        cluster   = r2.json()
        court_id  = cluster.get("court_id", "unknown")
        case_name = cluster.get("case_name", label)
        sub_ops   = cluster.get("sub_opinions", [])
        cl_url    = f"https://www.courtlistener.com/opinion/{cluster_id}/{slugify(case_name)}/"

        if not sub_ops:
            continue

        # Fetch first opinion
        r3 = cl_get(sub_ops[0])
        if r3.status_code != 200:
            continue
        opinion = r3.json()

        # --- Try PDF first ---
        pdf_rel = opinion.get("filepath_pdf_harvard") or ""
        if pdf_rel:
            pdf_url = pdf_rel if pdf_rel.startswith("http") else \
                      f"https://storage.courtlistener.com/{pdf_rel.lstrip('/')}"
            rp = fetch_pdf_url(pdf_url)
            if rp.status_code == 200 and rp.content[:4] == b"%PDF":
                print(f"    PDF hit  cluster={cluster_id}  court={court_id}")
                return cluster_id, court_id, case_name, cl_url, "pdf", rp.content

        # --- Try text ---
        raw = best_text(opinion)
        if raw:
            text = strip_html(raw) if "<" in raw else raw
            if len(text.strip()) >= MIN_CHARS:
                print(f"    TXT hit  cluster={cluster_id}  court={court_id}  "
                      f"({len(text):,} chars)")
                return cluster_id, court_id, case_name, cl_url, "txt", text

    return None


# ── Read existing manifest to preserve already-good rows ──────────────────────
existing_manifest = {}
mpath = os.path.join(OUT_DIR, "judgments_manifest.csv")
if os.path.exists(mpath):
    with open(mpath, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                idx = int(row["file_name"].split("_")[1])
                existing_manifest[idx] = row
            except (IndexError, ValueError):
                pass

new_rows  = {}
failed    = []

for (idx, name, court, statute, cite_q, kw_q) in CASES:
    slug   = slugify(name)
    prefix = f"judgment_{idx:02d}_{slug}"

    # Check existing file quality
    for ext in ("pdf", "txt"):
        candidate = os.path.join(OUT_DIR, f"{prefix}.{ext}")
        if os.path.exists(candidate) and os.path.getsize(candidate) >= GOOD_BYTES:
            print(f"[{idx:02d}/30] SKIP (good file exists) — {name}")
            if idx in existing_manifest:
                new_rows[idx] = existing_manifest[idx]
            else:
                new_rows[idx] = {
                    "id": "",
                    "file_name": f"{prefix}.{ext}",
                    "case_name": name,
                    "court": court,
                    "paired_statute": statute,
                    "file_type": ext,
                    "url": f"https://www.courtlistener.com/opinion//{slug}/",
                }
            break
    else:
        # Need to download (missing or bad)
        print(f"\n[{idx:02d}/30] {name}  [{court}]")

        # Delete stale file if present
        for ext in ("pdf", "txt"):
            stale = os.path.join(OUT_DIR, f"{prefix}.{ext}")
            if os.path.exists(stale):
                os.remove(stale)
                print(f"  removed stale {stale}")

        result = None

        # Strategy 1: citation string
        result = search_and_fetch(cite_q, name)

        # Strategy 2: full case name
        if result is None:
            result = search_and_fetch(f'"{name}"', name)

        # Strategy 3: keyword fallback
        if result is None and kw_q:
            result = search_and_fetch(kw_q, name)

        if result is None:
            print(f"  FAILED — no usable opinion found")
            failed.append(f"{idx:02d}|{name}|no_usable_result")
            continue

        cluster_id, court_id, api_name, cl_url, ftype, content = result
        file_name = f"{prefix}.{ftype}"
        out_path  = os.path.join(OUT_DIR, file_name)

        if ftype == "pdf":
            with open(out_path, "wb") as f:
                f.write(content)
            size_str = f"{len(content) // 1024} KB"
        else:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(content)
            size_str = f"{len(content):,} chars"

        print(f"  SAVED {ftype.upper()} ({size_str}) -> {file_name}")

        new_rows[idx] = {
            "id":             cluster_id,
            "file_name":      file_name,
            "case_name":      api_name,
            "court":          court_id,
            "paired_statute": statute,
            "file_type":      ftype,
            "url":            cl_url,
        }

# ── Write updated manifest ─────────────────────────────────────────────────────
with open(mpath, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f, fieldnames=["id","file_name","case_name","court","paired_statute","file_type","url"]
    )
    writer.writeheader()
    for idx in sorted(new_rows):
        writer.writerow(new_rows[idx])
print(f"\nManifest -> {mpath}  ({len(new_rows)} rows)")

# ── Write failed ───────────────────────────────────────────────────────────────
fpath = os.path.join(OUT_DIR, "failed.txt")
if failed:
    with open(fpath, "w", encoding="utf-8") as f:
        f.write("\n".join(failed) + "\n")
    print(f"Failed   -> {fpath}  ({len(failed)} cases)")
else:
    if os.path.exists(fpath):
        os.remove(fpath)
    print("No failures.")

# ── Final inventory ────────────────────────────────────────────────────────────
print("\n--- Final file inventory ---")
all_files = sorted(f for f in os.listdir(OUT_DIR)
                   if f.startswith("judgment_") and not f.endswith(".csv"))
total_good = 0
for fn in all_files:
    size = os.path.getsize(os.path.join(OUT_DIR, fn))
    flag = "  [SUSPICIOUS <5KB]" if size < GOOD_BYTES else ""
    print(f"  {size:>10,} B  {fn}{flag}")
    if size >= GOOD_BYTES:
        total_good += 1

print(f"\nTotal judgment files : {len(all_files)}")
print(f"Good (>= 5 KB)       : {total_good}")
print(f"Suspicious (< 5 KB)  : {len(all_files) - total_good}")
print("Done.")
