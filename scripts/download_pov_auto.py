import sys, requests, os, time, json

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

os.makedirs("data/raw/pov", exist_ok=True)

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/html",
    "Referer": "https://crsreports.congress.gov"
}

failures = []

# ── SECTION 1: CRS Reports ────────────────────────────────────────────────────
print("=== SECTION 1: CRS Reports ===")

crs_queries = [
    ("pov_crs_01_gross_income.pdf",    "gross income section 61"),
    ("pov_crs_02_business_expense.pdf","business expense section 162"),
    ("pov_crs_03_charitable.pdf",      "charitable contribution section 170"),
    ("pov_crs_04_exempt_orgs.pdf",     "tax exempt organizations 501c3"),
    ("pov_crs_05_like_kind.pdf",       "like kind exchange 1031"),
    ("pov_crs_06_capital_gains.pdf",   "capital gains tax"),
    ("pov_crs_07_ira.pdf",             "individual retirement account"),
    ("pov_crs_08_qbi.pdf",             "qualified business income 199A"),
    ("pov_crs_09_depreciation.pdf",    "depreciation section 167"),
    ("pov_crs_10_penalties.pdf",       "tax penalties section 6662"),
    ("pov_crs_11_reorg.pdf",           "corporate reorganization section 368"),
    ("pov_crs_12_hobby_loss.pdf",      "hobby loss section 183"),
]

for filename, query in crs_queries:
    path = f"data/raw/pov/{filename}"
    if os.path.exists(path) and os.path.getsize(path) > 10000:
        print(f"SKIP {filename}")
        continue
    try:
        url = f"https://crsreports.congress.gov/search/results?term={requests.utils.quote(query)}&pageSize=5"
        r = requests.get(url, headers=headers, timeout=30)
        print(f"CRS search '{query[:30]}' -> {r.status_code}")

        if r.status_code == 200:
            try:
                data = r.json()
                products = data.get("results", data.get("SearchResults", []))
                if products:
                    code = products[0].get("productNumber", products[0].get("ProductNumber", ""))
                    if code:
                        for pdf_url in [
                            f"https://crsreports.congress.gov/product/pdf/R/{code}",
                            f"https://crsreports.congress.gov/product/pdf/IF/{code}",
                            f"https://crsreports.congress.gov/product/pdf/RL/{code}",
                            f"https://crsreports.congress.gov/product/pdf/{code}",
                        ]:
                            pr = requests.get(pdf_url, headers=headers, timeout=60)
                            if pr.status_code == 200 and pr.content[:4] == b"%PDF":
                                open(path, "wb").write(pr.content)
                                print(f"  SAVED {filename} ({len(pr.content)//1024}KB)")
                                break
                            time.sleep(1)
                        else:
                            print(f"  PDF not found for {code}")
                            failures.append(f"CRS|{filename}|no_pdf_for_{code}")
                    else:
                        print(f"  No product code in result")
                        failures.append(f"CRS|{filename}|no_product_code")
                else:
                    print(f"  No results")
                    failures.append(f"CRS|{filename}|no_results")
            except Exception as je:
                print(f"  JSON parse failed: {je}")
                failures.append(f"CRS|{filename}|json_error|{je}")
        else:
            failures.append(f"CRS|{filename}|http_{r.status_code}")
    except Exception as e:
        print(f"  ERROR: {e}")
        failures.append(f"CRS|{filename}|exception|{e}")
    time.sleep(4)

# ── SECTION 2: GAO Reports ────────────────────────────────────────────────────
print("\n=== SECTION 2: GAO Reports ===")

gao_docs = [
    ("pov_gao_01_tax_exempt.pdf", "https://www.gao.gov/assets/gao-22-104756.pdf"),
    ("pov_gao_02_likekind.pdf",   "https://www.gao.gov/assets/gao-08-818.pdf"),
    ("pov_gao_03_retirement.pdf", "https://www.gao.gov/assets/gao-21-239.pdf"),
    ("pov_gao_04_penalties.pdf",  "https://www.gao.gov/assets/gao-20-248.pdf"),
    ("pov_gao_05_smallbiz.pdf",   "https://www.gao.gov/assets/gao-19-253.pdf"),
]

for name, url in gao_docs:
    path = f"data/raw/pov/{name}"
    if os.path.exists(path) and os.path.getsize(path) > 10000:
        print(f"SKIP {name}")
        continue
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        if r.status_code == 200 and r.content[:4] == b"%PDF":
            open(path, "wb").write(r.content)
            print(f"SAVED {name} ({len(r.content)//1024}KB)")
        else:
            print(f"FAILED {name} ({r.status_code})")
            failures.append(f"GAO|{name}|http_{r.status_code}")
    except Exception as e:
        print(f"ERROR {name}: {e}")
        failures.append(f"GAO|{name}|exception|{e}")
    time.sleep(3)

# ── SECTION 3: Tax Foundation ─────────────────────────────────────────────────
print("\n=== SECTION 3: Tax Foundation ===")

tf_docs = [
    ("pov_tf_01_199A.pdf",      "https://taxfoundation.org/wp-content/uploads/2021/05/Section-199A-Qualified-Business-Income-Deduction.pdf"),
    ("pov_tf_02_capgains.pdf",  "https://taxfoundation.org/wp-content/uploads/2022/03/Capital-Gains-Tax-Rates-2022.pdf"),
    ("pov_tf_03_corporate.pdf", "https://taxfoundation.org/wp-content/uploads/2022/08/corporate-tax.pdf"),
    ("pov_tf_04_charitable.pdf","https://taxfoundation.org/wp-content/uploads/2020/10/Charitable-Deduction.pdf"),
    ("pov_tf_05_1031.pdf",      "https://taxfoundation.org/wp-content/uploads/2021/08/Like-Kind-Exchanges.pdf"),
]

for name, url in tf_docs:
    path = f"data/raw/pov/{name}"
    if os.path.exists(path) and os.path.getsize(path) > 10000:
        print(f"SKIP {name}")
        continue
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        if r.status_code == 200 and r.content[:4] == b"%PDF":
            open(path, "wb").write(r.content)
            print(f"SAVED {name} ({len(r.content)//1024}KB)")
        else:
            print(f"FAILED {name} ({r.status_code})")
            failures.append(f"TaxFoundation|{name}|http_{r.status_code}|{url}")
    except Exception as e:
        print(f"ERROR {name}: {e}")
        failures.append(f"TaxFoundation|{name}|exception|{e}")
    time.sleep(3)

# ── SECTION 4: JCT via GovInfo ───────────────────────────────────────────────
print("\n=== SECTION 4: JCT Reports ===")

jct_docs = [
    ("pov_jct_01_tcja.pdf",        "https://www.congress.gov/115/crpt/jrpt1/CRPT-115jrpt1.pdf"),
    ("pov_jct_02_expenditures.pdf","https://www.jct.gov/CMSPages/GetFile.aspx?guid=6ce0a9a5-cd41-4ba5-baad-8a52b2e5bf0a"),
    ("pov_jct_03_charitable.pdf",  "https://www.jct.gov/CMSPages/GetFile.aspx?guid=d12a5e85-a410-4e7d-9627-9b7feff7aba4"),
    ("pov_jct_04_retirement.pdf",  "https://www.jct.gov/CMSPages/GetFile.aspx?guid=b3a5e7c2-1234-4567-89ab-cdef01234567"),
    ("pov_jct_05_corps.pdf",       "https://www.jct.gov/CMSPages/GetFile.aspx?guid=c4b6f8d3-2345-5678-9abc-def012345678"),
    ("pov_jct_06_capgains.pdf",    "https://www.jct.gov/CMSPages/GetFile.aspx?guid=d5c7g9e4-3456-6789-abcd-ef0123456789"),
    ("pov_jct_07_penalties.pdf",   "https://www.jct.gov/CMSPages/GetFile.aspx?guid=e6d8h0f5-4567-7890-bcde-f01234567890"),
]

for name, url in jct_docs:
    path = f"data/raw/pov/{name}"
    if os.path.exists(path) and os.path.getsize(path) > 10000:
        print(f"SKIP {name}")
        continue
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        if r.status_code == 200 and r.content[:4] == b"%PDF":
            open(path, "wb").write(r.content)
            print(f"SAVED {name} ({len(r.content)//1024}KB)")
        else:
            print(f"FAILED {name} ({r.status_code})")
            failures.append(f"JCT|{name}|http_{r.status_code}|{url}")
    except Exception as e:
        print(f"ERROR {name}: {e}")
        failures.append(f"JCT|{name}|exception|{e}")
    time.sleep(3)

# ── Write failures log ────────────────────────────────────────────────────────
if failures:
    with open("data/raw/pov/failed_pov.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(failures) + "\n")
    print(f"\nFailures logged to data/raw/pov/failed_pov.txt ({len(failures)} entries)")

# ── Final summary ─────────────────────────────────────────────────────────────
files = sorted(f for f in os.listdir("data/raw/pov") if f.endswith(".pdf"))
print(f"\n=== FINAL: {len(files)} PDFs in data/raw/pov/ ===")
for f in files:
    size = os.path.getsize(f"data/raw/pov/{f}") // 1024
    print(f"  {f} ({size}KB)")
