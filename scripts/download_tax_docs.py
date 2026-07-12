import requests, os, time

os.makedirs("data/raw/tax_docs", exist_ok=True)
headers = {"User-Agent": "Mozilla/5.0 Legal Research Project"}

docs = [
    ("tax_pub17.pdf",   "https://www.irs.gov/pub/irs-pdf/p17.pdf"),
    ("tax_pub535.pdf",  "https://www.irs.gov/pub/irs-pdf/p535.pdf"),
    ("tax_pub946.pdf",  "https://www.irs.gov/pub/irs-pdf/p946.pdf"),
    ("tax_pub526.pdf",  "https://www.irs.gov/pub/irs-pdf/p526.pdf"),
    ("tax_pub590a.pdf", "https://www.irs.gov/pub/irs-pdf/p590a.pdf"),
    ("tax_pub544.pdf",  "https://www.irs.gov/pub/irs-pdf/p544.pdf"),
    ("tax_pub463.pdf",  "https://www.irs.gov/pub/irs-pdf/p463.pdf"),
    ("tax_pub334.pdf",  "https://www.irs.gov/pub/irs-pdf/p334.pdf"),
    ("tax_pub550.pdf",  "https://www.irs.gov/pub/irs-pdf/p550.pdf"),
    ("tax_pub15b.pdf",  "https://www.irs.gov/pub/irs-pdf/p15b.pdf"),
]

for name, url in docs:
    path = f"data/raw/tax_docs/{name}"
    print(f"Downloading {name}...", end=" ")
    try:
        r = requests.get(url, headers=headers, timeout=60)
        if r.status_code == 200 and r.content[:4] == b"%PDF":
            with open(path, "wb") as f:
                f.write(r.content)
            print(f"SAVED ({len(r.content)//1024}KB)")
        else:
            print(f"FAILED ({r.status_code})")
    except Exception as e:
        print(f"ERROR: {e}")
    time.sleep(2)

print(f"\nTotal saved: {len(os.listdir('data/raw/tax_docs'))} files")
