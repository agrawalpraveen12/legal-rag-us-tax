import sys, requests, os, time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOKEN = "755ecc684849021f8273300142ec79eaba55765e"
headers = {"Authorization": f"Token {TOKEN}"}
BASE = "https://www.courtlistener.com/api/rest/v4"

cases = [
    ("judgment_08_gregory_v_helvering.txt",                       "Gregory Helvering",         "ca2"),
    ("judgment_09_cottage_savings_association_v_commissioner.txt", "Cottage Savings",           "scotus"),
    ("judgment_11_cheek_v_united_states.txt",                     "Cheek United States",        "scotus"),
    ("judgment_12_united_states_v_kirby_lumber.txt",              "Kirby Lumber",               "scotus"),
    ("judgment_13_faridessultaneh_v_commissioner.txt",            "Farid Sultaneh",             "ca2"),
    ("judgment_14_commissioner_v_duberstein.txt",                 "Duberstein",                 "scotus"),
    ("judgment_16_commissioner_v_tufts.txt",                      "Commissioner Tufts",         "scotus"),
    ("judgment_17_arrowsmith_v_commissioner.txt",                 "Arrowsmith Commissioner",    "scotus"),
    ("judgment_18_corn_products_refining_v_commissioner.txt",     "Corn Products Refining",     "scotus"),
    ("judgment_26_moller_v_united_states.txt",                    "Moller United States",       "uscfc"),
]

OUTPUT_DIR = "data/raw/judgments"
MIN_CHARS = 500

def get_text(opinion_id):
    r = requests.get(f"{BASE}/opinions/{opinion_id}/", headers=headers, timeout=30)
    if r.status_code != 200:
        return ""
    d = r.json()
    return (d.get("plain_text") or
            d.get("html_lawbox") or
            d.get("html_columbia") or
            d.get("html") or "")

for filename, query, court in cases:
    path = os.path.join(OUTPUT_DIR, filename)
    print(f"\n[{filename}]")

    # Delete stub
    if os.path.exists(path) and os.path.getsize(path) < 5000:
        os.remove(path)
        print(f"  Deleted stub")

    if os.path.exists(path) and os.path.getsize(path) >= 5000:
        print(f"  SKIP (already good)")
        continue

    found = False
    queries = [query, query.split()[0]]

    for q in queries:
        if found:
            break
        for use_court in [True, False]:
            if found:
                break
            params = {"q": q, "type": "o", "order_by": "score desc"}
            if use_court:
                params["court"] = court
            try:
                r = requests.get(f"{BASE}/search/", headers=headers, params=params, timeout=30)
                print(f"  search q={q!r} court={'yes' if use_court else 'no'} -> {r.status_code}", end=" ")

                if r.status_code == 429:
                    wait = int(r.headers.get("Retry-After", 60))
                    print(f"RATE LIMIT, sleeping {wait}s")
                    time.sleep(wait + 5)
                    continue

                if r.status_code != 200:
                    print()
                    continue

                results = r.json().get("results", [])
                if not results:
                    print("no results")
                    continue

                # Sort by citeCount, take best
                best = max(results[:5], key=lambda x: x.get("citeCount", 0))
                print(f"best='{best.get('caseName','')}' cites={best.get('citeCount',0)}", end=" ")

                # opinion ID is in opinions[0]['id'], NOT top-level id
                opinions_list = best.get("opinions", [])
                opinion_id = opinions_list[0]["id"] if opinions_list else None

                if not opinion_id:
                    print("no opinion id")
                    continue

                text = get_text(opinion_id)
                time.sleep(3)

                if len(text) >= MIN_CHARS:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(text)
                    kb = os.path.getsize(path) // 1024
                    print(f"SAVED {kb}KB")
                    found = True
                else:
                    print(f"text too short ({len(text)} chars)")

            except Exception as e:
                print(f"ERROR: {e}")

            time.sleep(5)

    if not found:
        print(f"  FAILED")
        with open(os.path.join(OUTPUT_DIR, "failed.txt"), "a", encoding="utf-8") as f:
            f.write(filename + "\n")

    print(f"  Sleeping 20s...")
    time.sleep(20)

# Summary
files = [f for f in os.listdir(OUTPUT_DIR) if f.endswith(".txt")]
good  = [f for f in files if os.path.getsize(os.path.join(OUTPUT_DIR, f)) >= 5000]
print(f"\n=== DONE: {len(good)} good files / {len(files)} total ===")
for f in sorted(good):
    kb = os.path.getsize(os.path.join(OUTPUT_DIR, f)) // 1024
    print(f"  {kb:>5}KB  {f}")
