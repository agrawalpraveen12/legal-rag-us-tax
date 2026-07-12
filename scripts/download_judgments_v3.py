"""
Judgment downloader v3 — robust recovery script.

Changes vs v2:
  - Never deletes an existing file until a replacement is confirmed saved.
  - 25-second sleep between every API call.
  - 90-second back-off + single retry on HTTP 429.
  - Timeout errors handled gracefully (skip, log to failed.txt).
  - Only fetches ONE cluster+opinion per search hit (not 5).
  - Checks content fields in-order: plain_text > html_with_citations > html_lawbox.
  - MIN_CONTENT raised to 1000 chars to reject stub orders.
"""

import sys, requests, os, time, csv, re, traceback

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API_TOKEN  = "755ecc684849021f8273300142ec79eaba55765e"
BASE       = "https://www.courtlistener.com/api/rest/v4"
OUT_DIR    = "data/raw/judgments"
SLEEP      = 25          # seconds between every API call
BACKOFF    = 90          # seconds to wait after 429
MIN_CHARS  = 1000        # reject opinions shorter than this
GOOD_BYTES = 5120        # existing files >= this are kept as-is

os.makedirs(OUT_DIR, exist_ok=True)

HDR = {
    "Authorization": f"Token {API_TOKEN}",
    "User-Agent": "data-collection-research/1.0",
}

# ── Case list ─────────────────────────────────────────────────────────────────
# (idx, display_name, court, statute, primary_query, fallback_query)
# primary_query  = citation string  →  most precise
# fallback_query = keywords         →  used only if primary fails
CASES = [
    ( 1, "Commissioner v Glenshaw Glass",              "scotus","IRC §61",
         "Commissioner v Glenshaw Glass 348 US 426",   "Glenshaw Glass gross income"),
    ( 2, "Old Colony Trust Co v Commissioner",         "scotus","IRC §61",
         "Old Colony Trust Co v Commissioner 279 US 716","Old Colony Trust employer tax payment income"),
    ( 3, "Cesarini v United States",                   "ca6",  "IRC §61",
         "Cesarini v United States 296 F Supp 3",      "Cesarini found money gross income"),
    ( 4, "Welch v Helvering",                          "scotus","IRC §162",
         "Welch v Helvering 290 US 111",               "Welch Helvering ordinary necessary business expense"),
    ( 5, "Commissioner v Tellier",                     "scotus","IRC §162",
         "Commissioner v Tellier 383 US 687",          "Tellier legal fees criminal deduction"),
    ( 6, "INDOPCO v Commissioner",                     "scotus","IRC §162",
         "INDOPCO v Commissioner 503 US 79",           "INDOPCO capitalization future benefit"),
    ( 7, "Bob Jones University v United States",       "scotus","IRC §501",
         "Bob Jones University v United States 461 US 574","Bob Jones University exempt racial discrimination"),
    ( 8, "Gregory v Helvering",                        "scotus","IRC §368",
         "Gregory v Helvering 293 US 465",             "Gregory Helvering reorganization sham substance"),
    ( 9, "Cottage Savings Association v Commissioner", "scotus","IRC §1001",
         "Cottage Savings Association v Commissioner 499 US 554","Cottage Savings realization materially different property"),
    (10, "Starker v United States",                    "ca9",  "IRC §1031",
         "Starker v United States 602 F2d 1341",       "Starker deferred like kind exchange"),
    (11, "Cheek v United States",                      "scotus","IRC §7201",
         "Cheek v United States 498 US 192",           "Cheek willfulness tax evasion good faith"),
    (12, "United States v Kirby Lumber",               "scotus","IRC §61",
         "United States v Kirby Lumber 284 US 1",      "Kirby Lumber debt discharge cancellation gross income"),
    (13, "Farid-Es-Sultaneh v Commissioner",           "ca2",  "IRC §102",
         "Farid-Es-Sultaneh v Commissioner 160 F2d 812","Farid Sultaneh prenuptial stock basis gift"),
    (14, "Commissioner v Duberstein",                  "scotus","IRC §102",
         "Commissioner v Duberstein 363 US 278",       "Duberstein gift dominant motive transferor"),
    (15, "Crane v Commissioner",                       "scotus","IRC §1001",
         "Crane v Commissioner 331 US 1",              "Crane encumbered property basis mortgage"),
    (16, "Commissioner v Tufts",                       "scotus","IRC §1001",
         "Commissioner v Tufts 461 US 300",            "Tufts nonrecourse mortgage exceeds value"),
    (17, "Arrowsmith v Commissioner",                  "scotus","IRC §1221",
         "Arrowsmith v Commissioner 344 US 6",         "Arrowsmith character loss related transaction"),
    (18, "Corn Products Refining v Commissioner",      "scotus","IRC §1221",
         "Corn Products Refining v Commissioner 350 US 46","Corn Products futures ordinary integral business"),
    (19, "Arkansas Best Corporation v Commissioner",   "scotus","IRC §1221",
         "Arkansas Best Corporation v Commissioner 485 US 212","Arkansas Best stock capital asset purpose"),
    (20, "Grodt McKay Realty v Commissioner",          "tax",  "IRC §1031",
         "Grodt McKay Realty v Commissioner 77 TC 1221","Grodt McKay like kind exchange ownership"),
    (21, "Estate of Franklin v Commissioner",          "ca9",  "IRC §167",
         "Estate of Franklin v Commissioner 544 F2d 1045","Estate Franklin nonrecourse depreciation shelter"),
    (22, "United States v Gilmore",                    "scotus","IRC §165",
         "United States v Gilmore 372 US 39",          "Gilmore divorce legal origin of claim deduction"),
    (23, "Commissioner v Flowers",                     "scotus","IRC §162",
         "Commissioner v Flowers 326 US 465",          "Flowers travel away from home tax home"),
    (24, "Hernandez v Commissioner",                   "scotus","IRC §170",
         "Hernandez v Commissioner 490 US 680",        "Hernandez quid pro quo charitable deduction"),
    (25, "Benaglia v Commissioner",                    "bta",  "IRC §61",
         "Benaglia v Commissioner 36 BTA 838",         "Benaglia meals lodging hotel manager exclusion"),
    (26, "Moller v United States",                     "uscfc","IRC §183",
         "Moller v United States 721 F2d 810",         "Moller hobby loss profit motive activity"),
    (27, "Textron Inc v United States",                "ca1",  "IRC §6662",
         "Textron Inc v United States 577 F3d 21",     "Textron work product privilege tax accrual"),
    (28, "Helvering v Bruun",                          "scotus","IRC §61",
         "Helvering v Bruun 309 US 461",               "Bruun lease forfeiture improvement realization"),
    (29, "Davis v United States",                      "scotus","IRC §170",
         "Davis v United States 495 US 472",           "Davis charitable gift appreciated stock"),
    (30, "Commissioner v Idaho Power",                 "scotus","IRC §263",
         "Commissioner v Idaho Power 418 US 1",        "Idaho Power capital expenditure self-constructed"),
]


def slugify(name):
    s = name.lower()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    s = re.sub(r"\s+", "_", s.strip())
    return s


def api_get(url, params=None):
    """GET with auth + 25s sleep. Returns (response, error_str)."""
    try:
        r = requests.get(url, headers=HDR, params=params, timeout=45)
    except requests.exceptions.Timeout:
        time.sleep(SLEEP)
        return None, "timeout"
    except Exception as e:
        time.sleep(SLEEP)
        return None, str(e)

    if r.status_code == 429:
        print(f"    429 rate-limited — backing off {BACKOFF}s ...")
        time.sleep(BACKOFF)
        # one retry
        try:
            r = requests.get(url, headers=HDR, params=params, timeout=45)
        except Exception as e:
            time.sleep(SLEEP)
            return None, str(e)
        if r.status_code == 429:
            time.sleep(SLEEP)
            return None, "429 after retry"

    time.sleep(SLEEP)
    return r, None


def pdf_get(url):
    """Download a PDF from storage CDN."""
    try:
        r = requests.get(url, timeout=90)
    except requests.exceptions.Timeout:
        time.sleep(SLEEP)
        return None, "timeout"
    except Exception as e:
        time.sleep(SLEEP)
        return None, str(e)
    time.sleep(SLEEP)
    return r, None


def extract_text(opinion: dict) -> str:
    """Best available text from opinion dict, stripped of HTML."""
    for field in ("plain_text", "html_with_citations", "html_lawbox", "html_anon_2020"):
        val = (opinion.get(field) or "").strip()
        if val:
            # Strip HTML tags if present
            clean = re.sub(r"<[^>]+>", " ", val)
            clean = re.sub(r"\s{2,}", " ", clean).strip()
            if len(clean) >= MIN_CHARS:
                return clean
    return ""


def try_download(query: str):
    """
    Search → pick best result → fetch opinion → return content.
    Returns dict with keys: cluster_id, court_id, case_name, cl_url, ftype, content
    or None if nothing usable.
    """
    print(f"    SEARCH: {query!r}")
    r, err = api_get(f"{BASE}/search/", {"q": query, "type": "o", "order_by": "citeCount desc"})
    if err or r is None:
        print(f"    search failed: {err}")
        return None
    if r.status_code != 200:
        print(f"    search HTTP {r.status_code}")
        return None

    results = r.json().get("results", [])
    if not results:
        print(f"    0 results")
        return None

    # Sort by citeCount descending; default 0 if absent
    results.sort(key=lambda x: x.get("citeCount", 0), reverse=True)
    top_cite = results[0].get("citeCount", "?")
    print(f"    {len(results)} hits, top citeCount={top_cite}")

    # Try top 3 results
    for res in results[:3]:
        cluster_id = res.get("cluster_id") or res.get("id")
        if not cluster_id:
            continue

        # ── Fetch cluster ──────────────────────────────────────────────────
        r2, err2 = api_get(f"{BASE}/clusters/{cluster_id}/")
        if err2 or r2 is None:
            print(f"    cluster {cluster_id} failed: {err2}")
            continue
        if r2.status_code != 200:
            print(f"    cluster {cluster_id} HTTP {r2.status_code}")
            continue

        cluster  = r2.json()
        court_id = cluster.get("court_id", "unknown")
        api_name = cluster.get("case_name", "")
        sub_ops  = cluster.get("sub_opinions", [])
        cl_url   = f"https://www.courtlistener.com/opinion/{cluster_id}/{slugify(api_name)}/"

        if not sub_ops:
            print(f"    cluster {cluster_id}: no sub_opinions")
            continue

        # ── Fetch opinion ──────────────────────────────────────────────────
        r3, err3 = api_get(sub_ops[0])
        if err3 or r3 is None:
            print(f"    opinion fetch failed: {err3}")
            continue
        if r3.status_code != 200:
            print(f"    opinion HTTP {r3.status_code}")
            continue

        opinion = r3.json()

        # ── Try PDF first ──────────────────────────────────────────────────
        pdf_rel = opinion.get("filepath_pdf_harvard") or ""
        if pdf_rel:
            pdf_url = pdf_rel if pdf_rel.startswith("http") else \
                      f"https://storage.courtlistener.com/{pdf_rel.lstrip('/')}"
            rp, ep = pdf_get(pdf_url)
            if rp and rp.status_code == 200 and rp.content[:4] == b"%PDF":
                print(f"    PDF ok  cluster={cluster_id}  court={court_id}  "
                      f"({len(rp.content)//1024} KB)")
                return dict(cluster_id=cluster_id, court_id=court_id,
                            case_name=api_name, cl_url=cl_url,
                            ftype="pdf", content=rp.content)

        # ── Try text ───────────────────────────────────────────────────────
        text = extract_text(opinion)
        if text:
            print(f"    TXT ok  cluster={cluster_id}  court={court_id}  "
                  f"({len(text):,} chars)")
            return dict(cluster_id=cluster_id, court_id=court_id,
                        case_name=api_name, cl_url=cl_url,
                        ftype="txt", content=text)

        print(f"    cluster {cluster_id}: content too short, trying next ...")

    return None


# ── Load existing manifest ─────────────────────────────────────────────────────
mpath = os.path.join(OUT_DIR, "judgments_manifest.csv")
existing = {}
if os.path.exists(mpath):
    with open(mpath, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            fn = row.get("file_name", "")
            parts = fn.split("_")
            if len(parts) >= 2 and parts[1].isdigit():
                existing[int(parts[1])] = row

manifest_rows = {}
failed_cases  = []

# ── Main loop ─────────────────────────────────────────────────────────────────
for (idx, name, court, statute, primary_q, fallback_q) in CASES:
    slug   = slugify(name)
    prefix = f"judgment_{idx:02d}_{slug}"

    # Check if a good file already exists
    for ext in ("pdf", "txt"):
        path = os.path.join(OUT_DIR, f"{prefix}.{ext}")
        if os.path.exists(path) and os.path.getsize(path) >= GOOD_BYTES:
            print(f"[{idx:02d}/30] OK (already good) — {name}")
            manifest_rows[idx] = existing.get(idx, {
                "id": "", "file_name": f"{prefix}.{ext}",
                "case_name": name, "court": court,
                "paired_statute": statute, "file_type": ext,
                "url": f"https://www.courtlistener.com/opinion//{slug}/",
            })
            break
    else:
        print(f"\n[{idx:02d}/30] {name}  [{court}]  — needs download")

        result = try_download(primary_q)
        if result is None:
            print(f"  primary failed, trying fallback ...")
            result = try_download(fallback_q)

        if result is None:
            print(f"  FAILED — no usable opinion found")
            failed_cases.append(f"{idx:02d}|{name}|no_usable_result")
            continue

        # Save — only now remove any stale file
        new_file = f"{prefix}.{result['ftype']}"
        new_path = os.path.join(OUT_DIR, new_file)

        for old_ext in ("pdf", "txt"):
            old = os.path.join(OUT_DIR, f"{prefix}.{old_ext}")
            if os.path.exists(old):
                os.remove(old)

        if result["ftype"] == "pdf":
            with open(new_path, "wb") as f:
                f.write(result["content"])
            size_str = f"{len(result['content'])//1024} KB"
        else:
            with open(new_path, "w", encoding="utf-8") as f:
                f.write(result["content"])
            size_str = f"{len(result['content']):,} chars"

        print(f"  SAVED {result['ftype'].upper()} ({size_str}) -> {new_file}")

        manifest_rows[idx] = {
            "id":             result["cluster_id"],
            "file_name":      new_file,
            "case_name":      result["case_name"] or name,
            "court":          result["court_id"] or court,
            "paired_statute": statute,
            "file_type":      result["ftype"],
            "url":            result["cl_url"],
        }

# ── Write manifest ─────────────────────────────────────────────────────────────
fields = ["id","file_name","case_name","court","paired_statute","file_type","url"]
with open(mpath, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    for i in sorted(manifest_rows):
        w.writerow(manifest_rows[i])
print(f"\nManifest -> {mpath}  ({len(manifest_rows)} rows)")

# ── Write failed.txt ───────────────────────────────────────────────────────────
fpath = os.path.join(OUT_DIR, "failed.txt")
if failed_cases:
    with open(fpath, "w", encoding="utf-8") as f:
        f.write("\n".join(failed_cases) + "\n")
    print(f"Failed   -> {fpath}  ({len(failed_cases)} cases)")
else:
    if os.path.exists(fpath):
        os.remove(fpath)
    print("No failures.")

# ── Final inventory ────────────────────────────────────────────────────────────
print("\n--- Final inventory ---")
all_j = sorted(f for f in os.listdir(OUT_DIR)
               if f.startswith("judgment_") and not f.endswith(".csv"))
good = 0
for fn in all_j:
    sz = os.path.getsize(os.path.join(OUT_DIR, fn))
    flag = "  [<5KB SUSPICIOUS]" if sz < GOOD_BYTES else ""
    print(f"  {sz/1024:7.1f} KB  {fn}{flag}")
    if sz >= GOOD_BYTES:
        good += 1
print(f"\nTotal files : {len(all_j)}/30")
print(f"Good >=5 KB : {good}")
print(f"Suspicious  : {len(all_j)-good}")
print("Done.")
