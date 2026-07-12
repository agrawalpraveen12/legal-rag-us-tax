"""
Judgment downloader v4.
Key change: uses /clusters/ REST endpoint (filtered lookup) instead of
/search/ (Elasticsearch) — different rate-limit bucket, avoids the 429s.

For each case:
  1. GET /clusters/?case_name=<name>&order_by=-citation_count
     → pick first result with enough content
  2. Fallback: try the opinion directly via /opinions/?cluster=<id>
  3. 25-second sleep after every API call.
  4. 120-second back-off + single retry on 429.
  5. Never deletes an existing file until replacement is confirmed.
"""

import sys, requests, os, time, csv, re

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API_TOKEN  = "755ecc684849021f8273300142ec79eaba55765e"
BASE       = "https://www.courtlistener.com/api/rest/v4"
OUT_DIR    = "data/raw/judgments"
SLEEP      = 25
BACKOFF    = 120
MIN_CHARS  = 1000
GOOD_BYTES = 5120

os.makedirs(OUT_DIR, exist_ok=True)

HDR = {
    "Authorization": f"Token {API_TOKEN}",
    "User-Agent": "data-collection-research/1.0",
}

# (idx, display_name, court_filter, statute, cluster_name_query, alt_name_query)
# cluster_name_query → sent as case_name= to /clusters/
# alt_name_query     → tried if primary returns 0 results
CASES = [
    ( 1,"Commissioner v Glenshaw Glass",          "scotus","IRC §61",
       "Commissioner v Glenshaw Glass",           "Glenshaw Glass"),
    ( 2,"Old Colony Trust Co v Commissioner",     "scotus","IRC §61",
       "Old Colony Trust Co v Commissioner",      "Old Colony Trust"),
    ( 3,"Cesarini v United States",               "ca6",  "IRC §61",
       "Cesarini v United States",                "Cesarini"),
    ( 4,"Welch v Helvering",                      "scotus","IRC §162",
       "Welch v Helvering",                       "Welch Helvering"),
    ( 5,"Commissioner v Tellier",                 "scotus","IRC §162",
       "Commissioner v Tellier",                  "Tellier"),
    ( 6,"INDOPCO v Commissioner",                 "scotus","IRC §162",
       "INDOPCO, Inc v Commissioner",             "INDOPCO Commissioner"),
    ( 7,"Bob Jones University v United States",   "scotus","IRC §501",
       "Bob Jones University v United States",    "Bob Jones University"),
    ( 8,"Gregory v Helvering",                    "scotus","IRC §368",
       "Gregory v Helvering",                     "Gregory Helvering"),
    ( 9,"Cottage Savings Association v Commissioner","scotus","IRC §1001",
       "Cottage Savings Association v Commissioner","Cottage Savings"),
    (10,"Starker v United States",                "ca9",  "IRC §1031",
       "Starker v United States",                 "Starker"),
    (11,"Cheek v United States",                  "scotus","IRC §7201",
       "Cheek v United States",                   "Cheek"),
    (12,"United States v Kirby Lumber Co",        "scotus","IRC §61",
       "United States v Kirby Lumber",            "Kirby Lumber"),
    (13,"Farid-Es-Sultaneh v Commissioner",       "ca2",  "IRC §102",
       "Farid-Es-Sultaneh v Commissioner",        "Farid Sultaneh"),
    (14,"Commissioner v Duberstein",              "scotus","IRC §102",
       "Commissioner v Duberstein",               "Duberstein"),
    (15,"Crane v Commissioner",                   "scotus","IRC §1001",
       "Crane v Commissioner",                    "Crane Commissioner"),
    (16,"Commissioner v Tufts",                   "scotus","IRC §1001",
       "Commissioner v Tufts",                    "Tufts"),
    (17,"Arrowsmith v Commissioner",              "scotus","IRC §1221",
       "Arrowsmith v Commissioner",               "Arrowsmith"),
    (18,"Corn Products Refining Co v Commissioner","scotus","IRC §1221",
       "Corn Products Refining Co v Commissioner","Corn Products"),
    (19,"Arkansas Best Corp v Commissioner",      "scotus","IRC §1221",
       "Arkansas Best Corporation v Commissioner","Arkansas Best"),
    (20,"Grodt & McKay Realty v Commissioner",    "tax",  "IRC §1031",
       "Grodt & McKay Realty v Commissioner",     "Grodt McKay"),
    (21,"Estate of Franklin v Commissioner",      "ca9",  "IRC §167",
       "Estate of Franklin v Commissioner",       "Franklin Commissioner"),
    (22,"United States v Gilmore",                "scotus","IRC §165",
       "United States v Gilmore",                 "Gilmore"),
    (23,"Commissioner v Flowers",                 "scotus","IRC §162",
       "Commissioner v Flowers",                  "Flowers Commissioner"),
    (24,"Hernandez v Commissioner",               "scotus","IRC §170",
       "Hernandez v Commissioner",                "Hernandez"),
    (25,"Benaglia v Commissioner",                "bta",  "IRC §61",
       "Benaglia v Commissioner",                 "Benaglia"),
    (26,"Moller v United States",                 "uscfc","IRC §183",
       "Moller v United States",                  "Moller"),
    (27,"Textron Inc v United States",            "ca1",  "IRC §6662",
       "Textron Inc v United States",             "Textron"),
    (28,"Helvering v Bruun",                      "scotus","IRC §61",
       "Helvering v Bruun",                       "Bruun"),
    (29,"Davis v United States",                  "scotus","IRC §170",
       "Davis v United States",                   "Davis"),
    (30,"Commissioner v Idaho Power Co",          "scotus","IRC §263",
       "Commissioner v Idaho Power",              "Idaho Power"),
]


def slugify(name):
    s = name.lower()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    return re.sub(r"\s+", "_", s.strip())


def api_get(url, params=None, label=""):
    """GET + sleep. Returns (response_or_None, error_str)."""
    try:
        r = requests.get(url, headers=HDR, params=params, timeout=45)
    except requests.exceptions.Timeout:
        print(f"    timeout on {label or url}")
        time.sleep(SLEEP)
        return None, "timeout"
    except Exception as e:
        print(f"    error on {label or url}: {e}")
        time.sleep(SLEEP)
        return None, str(e)

    if r.status_code == 429:
        retry_after = int(r.headers.get("Retry-After", BACKOFF))
        wait = max(retry_after, BACKOFF)
        print(f"    429 — waiting {wait}s before retry ...")
        time.sleep(wait)
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


def get_text(opinion: dict) -> str:
    for field in ("plain_text", "html_with_citations", "html_lawbox", "html_anon_2020"):
        raw = (opinion.get(field) or "").strip()
        if raw:
            clean = re.sub(r"<[^>]+>", " ", raw)
            clean = re.sub(r"\s{2,}", " ", clean).strip()
            if len(clean) >= MIN_CHARS:
                return clean
    return ""


def fetch_opinion_content(cluster_id, cluster_name):
    """Fetch the first opinion for a cluster. Returns (ftype, content) or (None, None)."""
    slug = slugify(cluster_name or str(cluster_id))
    cl_url = f"https://www.courtlistener.com/opinion/{cluster_id}/{slug}/"

    # Get opinions for this cluster
    r, err = api_get(f"{BASE}/opinions/", {"cluster": cluster_id}, "opinions")
    if err or not r or r.status_code != 200:
        return None, None, cl_url

    opinions = r.json().get("results", [])
    if not opinions:
        return None, None, cl_url

    opinion = opinions[0]

    # Try PDF
    pdf_rel = opinion.get("filepath_pdf_harvard") or ""
    if pdf_rel:
        pdf_url = pdf_rel if pdf_rel.startswith("http") else \
                  f"https://storage.courtlistener.com/{pdf_rel.lstrip('/')}"
        try:
            rp = requests.get(pdf_url, timeout=90)
            time.sleep(SLEEP)
            if rp.status_code == 200 and rp.content[:4] == b"%PDF":
                return "pdf", rp.content, cl_url
        except Exception:
            time.sleep(SLEEP)

    # Try text
    text = get_text(opinion)
    if text:
        return "txt", text, cl_url

    return None, None, cl_url


def lookup_cluster(name_query, court_filter):
    """
    Use /clusters/ REST endpoint to find the best matching cluster.
    Returns (cluster_id, case_name) or (None, None).
    """
    params = {
        "case_name": name_query,
        "order_by":  "-citation_count",
        "page_size": 5,
    }
    if court_filter:
        params["docket__court__id"] = court_filter

    print(f"    LOOKUP /clusters/ name={name_query!r} court={court_filter}")
    r, err = api_get(f"{BASE}/clusters/", params, "clusters")
    if err or not r or r.status_code != 200:
        print(f"    clusters API failed: {err or r.status_code if r else '?'}")
        return None, None

    results = r.json().get("results", [])
    print(f"    {len(results)} cluster(s) returned")
    if not results:
        return None, None

    # Pick highest citation count
    best = max(results, key=lambda x: x.get("citation_count", 0))
    cid  = best.get("id")
    cname = best.get("case_name", name_query)
    print(f"    best: cluster={cid}  cite_count={best.get('citation_count','?')}  name={cname!r}")
    return cid, cname


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
for (idx, name, court, statute, primary_q, alt_q) in CASES:
    slug   = slugify(name)
    prefix = f"judgment_{idx:02d}_{slug}"

    # Check for an already-good file
    for ext in ("pdf", "txt"):
        path = os.path.join(OUT_DIR, f"{prefix}.{ext}")
        if os.path.exists(path) and os.path.getsize(path) >= GOOD_BYTES:
            print(f"[{idx:02d}/30] OK (good file) — {name}")
            manifest_rows[idx] = existing.get(idx, {
                "id": "", "file_name": f"{prefix}.{ext}",
                "case_name": name, "court": court,
                "paired_statute": statute, "file_type": ext,
                "url": "",
            })
            break
    else:
        print(f"\n[{idx:02d}/30] {name}  [{court}]  — downloading")

        # Strategy 1: primary name + court filter
        cluster_id, cluster_name = lookup_cluster(primary_q, court)

        # Strategy 2: alt name + court filter
        if not cluster_id:
            cluster_id, cluster_name = lookup_cluster(alt_q, court)

        # Strategy 3: primary name, no court filter
        if not cluster_id:
            cluster_id, cluster_name = lookup_cluster(primary_q, None)

        if not cluster_id:
            print(f"  FAILED — cluster not found")
            failed_cases.append(f"{idx:02d}|{name}|cluster_not_found")
            continue

        ftype, content, cl_url = fetch_opinion_content(cluster_id, cluster_name)

        if not content:
            print(f"  FAILED — no content in cluster {cluster_id}")
            failed_cases.append(f"{idx:02d}|{name}|no_content|cluster={cluster_id}")
            continue

        size_str = (f"{len(content)//1024} KB" if ftype == "pdf"
                    else f"{len(content):,} chars")

        # Confirmed content — now safe to remove stale file and save
        for old_ext in ("pdf", "txt"):
            old = os.path.join(OUT_DIR, f"{prefix}.{old_ext}")
            if os.path.exists(old):
                os.remove(old)

        new_file = f"{prefix}.{ftype}"
        new_path = os.path.join(OUT_DIR, new_file)

        if ftype == "pdf":
            with open(new_path, "wb") as f:
                f.write(content)
        else:
            with open(new_path, "w", encoding="utf-8") as f:
                f.write(content)

        print(f"  SAVED {ftype.upper()} ({size_str}) -> {new_file}")

        manifest_rows[idx] = {
            "id":             cluster_id,
            "file_name":      new_file,
            "case_name":      cluster_name or name,
            "court":          court,
            "paired_statute": statute,
            "file_type":      ftype,
            "url":            cl_url,
        }

# ── Manifest ───────────────────────────────────────────────────────────────────
fields = ["id","file_name","case_name","court","paired_statute","file_type","url"]
with open(mpath, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    for i in sorted(manifest_rows):
        w.writerow(manifest_rows[i])
print(f"\nManifest -> {mpath}  ({len(manifest_rows)} rows)")

# ── Failed ─────────────────────────────────────────────────────────────────────
fpath = os.path.join(OUT_DIR, "failed.txt")
if failed_cases:
    with open(fpath, "w", encoding="utf-8") as f:
        f.write("\n".join(failed_cases) + "\n")
    print(f"Failed   -> {fpath}")
    for ln in failed_cases:
        print(f"  {ln}")
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
