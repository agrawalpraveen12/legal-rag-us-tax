import sys, requests, os, time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

os.makedirs("data/raw/pov", exist_ok=True)
h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

BASE_IRS   = "https://www.irs.gov/pub/irs-drop"
BASE_OTA   = "https://home.treasury.gov/system/files/131"
BASE_GREEN = "https://home.treasury.gov/system/files/131"
BASE_IRSPDF= "https://www.irs.gov/pub/irs-pdf"

# All 29 files: (output_name, url)
docs = [
    # ── SECTION 1: CRS substitutes → IRS Revenue Rulings & Notices (12) ──────
    ("pov_crs_01_gross_income.pdf",    f"{BASE_IRS}/rr-19-11.pdf"),
    ("pov_crs_02_business_expense.pdf",f"{BASE_IRS}/rr-14-02.pdf"),
    ("pov_crs_03_charitable.pdf",      f"{BASE_IRS}/n-23-75.pdf"),
    ("pov_crs_04_exempt_orgs.pdf",     f"{BASE_IRS}/n-21-56.pdf"),
    ("pov_crs_05_like_kind.pdf",       f"{BASE_IRS}/rr-04-86.pdf"),
    ("pov_crs_06_capital_gains.pdf",   f"{BASE_IRS}/n-23-08.pdf"),
    ("pov_crs_07_ira.pdf",             f"{BASE_IRS}/n-22-55.pdf"),
    ("pov_crs_08_qbi.pdf",             f"{BASE_IRS}/n-19-07.pdf"),
    ("pov_crs_09_depreciation.pdf",    f"{BASE_IRS}/rp-20-25.pdf"),
    ("pov_crs_10_penalties.pdf",       f"{BASE_IRS}/n-14-58.pdf"),
    ("pov_crs_11_reorg.pdf",           f"{BASE_IRS}/n-16-73.pdf"),
    ("pov_crs_12_hobby_loss.pdf",      f"{BASE_IRS}/n-09-11.pdf"),
    # ── SECTION 2: GAO substitutes → Treasury OTA Working Papers (5) ─────────
    ("pov_gao_01_tax_exempt.pdf",      f"{BASE_OTA}/WP-88.pdf"),
    ("pov_gao_02_likekind.pdf",        f"{BASE_OTA}/WP-89.pdf"),
    ("pov_gao_03_retirement.pdf",      f"{BASE_OTA}/WP-90.pdf"),
    ("pov_gao_04_penalties.pdf",       f"{BASE_OTA}/WP-91.pdf"),
    ("pov_gao_05_smallbiz.pdf",        f"{BASE_OTA}/WP-92.pdf"),
    # ── SECTION 3: Tax Foundation substitutes → Treasury GreenBook + IRS Pubs (5) ──
    ("pov_tf_01_199A.pdf",             f"{BASE_GREEN}/General-Explanations-FY2024.pdf"),
    ("pov_tf_02_capgains.pdf",         f"{BASE_GREEN}/General-Explanations-FY2023.pdf"),
    ("pov_tf_03_corporate.pdf",        f"{BASE_IRSPDF}/p542.pdf"),
    ("pov_tf_04_charitable.pdf",       f"{BASE_IRSPDF}/p538.pdf"),
    ("pov_tf_05_1031.pdf",             f"{BASE_IRS}/rp-23-34.pdf"),
    # ── SECTION 4: JCT substitutes → IRS Pubs + Rev Procs (7) ───────────────
    ("pov_jct_01_tcja.pdf",            f"{BASE_IRSPDF}/p551.pdf"),
    ("pov_jct_02_expenditures.pdf",    f"{BASE_IRSPDF}/p1212.pdf"),
    ("pov_jct_03_charitable.pdf",      f"{BASE_IRSPDF}/p575.pdf"),
    ("pov_jct_04_retirement.pdf",      f"{BASE_IRS}/rp-22-38.pdf"),
    ("pov_jct_05_corps.pdf",           f"{BASE_IRS}/rp-21-45.pdf"),
    ("pov_jct_06_capgains.pdf",        f"{BASE_IRS}/rr-23-14.pdf"),
    ("pov_jct_07_penalties.pdf",       f"{BASE_IRS}/n-21-07.pdf"),
]

saved, skipped, failed = 0, 0, []

for name, url in docs:
    path = f"data/raw/pov/{name}"
    if os.path.exists(path) and os.path.getsize(path) > 10000:
        print(f"SKIP  {name}")
        skipped += 1
        continue
    try:
        r = requests.get(url, headers=h, timeout=60)
        if r.status_code == 200 and r.content[:4] == b"%PDF":
            with open(path, "wb") as f:
                f.write(r.content)
            print(f"SAVED {name}  ({len(r.content)//1024}KB)")
            saved += 1
        else:
            print(f"FAIL  {name}  HTTP {r.status_code}  {url}")
            failed.append(f"{name}|{r.status_code}|{url}")
    except Exception as e:
        print(f"ERR   {name}  {e}")
        failed.append(f"{name}|exception|{e}")
    time.sleep(2)

if failed:
    with open("data/raw/pov/failed_pov_fixed.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(failed) + "\n")
    print(f"\n{len(failed)} failures -> data/raw/pov/failed_pov_fixed.txt")

files = sorted(f for f in os.listdir("data/raw/pov") if f.endswith(".pdf"))
print(f"\n=== DONE: {saved} saved, {skipped} skipped, {len(failed)} failed ===")
print(f"Total PDFs in data/raw/pov/: {len(files)}")
for f in files:
    kb = os.path.getsize(f"data/raw/pov/{f}") // 1024
    print(f"  {f}  ({kb}KB)")
