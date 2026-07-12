import requests, os, time, json

os.makedirs("data/raw/pov", exist_ok=True)
headers = {"User-Agent": "Mozilla/5.0 Legal Research Project"}

# PART 1 - IRS Taxpayer Advocate PDFs (direct download)
direct_docs = [
    ("pov_irs_01_sec162.pdf", "https://www.taxpayeradvocate.irs.gov/wp-content/uploads/2020/08/Most-Litigated-Issues-2-Trade-or-Business-Expenses-Under-IRC-162-and-Related-Sections.pdf"),
    ("pov_irs_02_sec183.pdf", "https://www.taxpayeradvocate.irs.gov/wp-content/uploads/2020/08/Most-Litigated-Issues-IRC-183-Not-for-Profit-Activities.pdf"),
    ("pov_irs_03_sec6662.pdf","https://www.taxpayeradvocate.irs.gov/wp-content/uploads/2020/08/Most-Litigated-Issues-Penalties-Under-IRC-6662.pdf"),
]

print("=== PART 1: IRS Direct PDFs ===")
for name, url in direct_docs:
    path = f"data/raw/pov/{name}"
    try:
        r = requests.get(url, headers=headers, timeout=60)
        if r.status_code == 200 and r.content[:4] == b"%PDF":
            open(path, "wb").write(r.content)
            print(f"SAVED {name} ({len(r.content)//1024}KB)")
        else:
            print(f"FAILED {name} ({r.status_code})")
    except Exception as e:
        print(f"ERROR {name}: {e}")
    time.sleep(2)

# PART 2 - CRS Reports via search API
print("\n=== PART 2: CRS Reports ===")
crs_topics = [
    ("pov_crs_01_gross_income.pdf",    "gross income tax overview section 61"),
    ("pov_crs_02_business_expense.pdf","business expense deduction section 162"),
    ("pov_crs_03_charitable.pdf",      "charitable contribution deduction section 170"),
    ("pov_crs_04_exempt_orgs.pdf",     "tax exempt organizations 501c3"),
    ("pov_crs_05_like_kind.pdf",       "like kind exchange section 1031"),
    ("pov_crs_06_capital_gains.pdf",   "capital gains tax"),
    ("pov_crs_07_ira.pdf",             "individual retirement account IRA section 408"),
    ("pov_crs_08_qbi.pdf",             "qualified business income deduction 199A"),
    ("pov_crs_09_depreciation.pdf",    "depreciation tax deduction section 167"),
    ("pov_crs_10_penalties.pdf",       "tax penalties accuracy related section 6662"),
    ("pov_crs_11_reorg.pdf",           "corporate reorganization tax section 368"),
    ("pov_crs_12_hobby_loss.pdf",      "hobby loss rules section 183"),
]

for filename, query in crs_topics:
    path = f"data/raw/pov/{filename}"
    print(f"Searching CRS: {query[:40]}...", end=" ")
    try:
        search_url = f"https://crsreports.congress.gov/search/results?term={requests.utils.quote(query)}&pageSize=5&pageNumber=1"
        r = requests.get(search_url, headers=headers, timeout=30)

        if r.status_code == 200:
            data = r.json()
            results = data.get("results", [])

            if results:
                product = results[0].get("productNumber") or results[0].get("id", "")
                if product:
                    pdf_url = f"https://crsreports.congress.gov/product/pdf/R/{product}"
                    pdf_r = requests.get(pdf_url, headers=headers, timeout=60)
                    if pdf_r.status_code == 200 and pdf_r.content[:4] == b"%PDF":
                        open(path, "wb").write(pdf_r.content)
                        print(f"SAVED {product} ({len(pdf_r.content)//1024}KB)")
                    else:
                        pdf_url2 = f"https://crsreports.congress.gov/product/pdf/{product}"
                        pdf_r2 = requests.get(pdf_url2, headers=headers, timeout=60)
                        if pdf_r2.status_code == 200 and pdf_r2.content[:4] == b"%PDF":
                            open(path, "wb").write(pdf_r2.content)
                            print(f"SAVED {product} ({len(pdf_r2.content)//1024}KB)")
                        else:
                            print(f"PDF FAILED ({pdf_r.status_code})")
                else:
                    print(f"No product code found")
            else:
                print(f"No results")
        else:
            print(f"Search FAILED ({r.status_code})")
    except Exception as e:
        print(f"ERROR: {e}")
    time.sleep(4)

# PART 3 - GAO Reports (direct)
print("\n=== PART 3: GAO Reports ===")
gao_docs = [
    ("pov_gao_01_tax_exempt.pdf",  "https://www.gao.gov/assets/gao-22-104756.pdf"),
    ("pov_gao_02_likekind.pdf",    "https://www.gao.gov/assets/gao-08-818.pdf"),
    ("pov_gao_03_retirement.pdf",  "https://www.gao.gov/assets/gao-21-239.pdf"),
    ("pov_gao_04_penalties.pdf",   "https://www.gao.gov/assets/gao-20-248.pdf"),
    ("pov_gao_05_small_biz.pdf",   "https://www.gao.gov/assets/gao-19-253.pdf"),
]

for name, url in gao_docs:
    path = f"data/raw/pov/{name}"
    try:
        r = requests.get(url, headers=headers, timeout=60)
        if r.status_code == 200 and r.content[:4] == b"%PDF":
            open(path, "wb").write(r.content)
            print(f"SAVED {name} ({len(r.content)//1024}KB)")
        else:
            print(f"FAILED {name} ({r.status_code})")
    except Exception as e:
        print(f"ERROR {name}: {e}")
    time.sleep(3)

# Final count
saved = os.listdir("data/raw/pov")
print(f"\n=== DONE: {len(saved)} files in data/raw/pov/ ===")
for f in sorted(saved):
    size = os.path.getsize(f"data/raw/pov/{f}") // 1024
    print(f"  {f} ({size}KB)")
