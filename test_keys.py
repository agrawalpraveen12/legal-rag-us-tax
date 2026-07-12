"""
Quick check: are all 4 Groq keys live?
Uses 8B model (tiny call) to conserve 70B quota.
"""

import os
from groq import Groq
from dotenv import load_dotenv
load_dotenv()

KEYS = {
    "PRIMARY":  os.getenv("GROQ_API_KEY_PRIMARY"),
    "FALLBACK": os.getenv("GROQ_API_KEY_FALLBACK"),
    "KEY_3":    os.getenv("GROQ_API_KEY_3"),
    "KEY_4":    os.getenv("GROQ_API_KEY_4"),
}

TPD_PER_KEY = 131_072   # tokens/day per free key (70B model)

print("=" * 55)
print("Groq Key Status Check")
print("=" * 55)

working = 0
for name, key in KEYS.items():
    if not key:
        print(f"  {name:8}: [NOT SET]")
        continue
    masked = key[:8] + "..." + key[-4:]
    try:
        client = Groq(api_key=key)
        r = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": "Say OK"}],
            max_tokens=5,
        )
        reply = r.choices[0].message.content.strip()
        print(f"  {name:8}: [OK]  {masked}  -> {reply}")
        working += 1
    except Exception as e:
        short = str(e)[:80]
        print(f"  {name:8}: [FAIL] {masked}  -> {short}")

print("-" * 55)
print(f"  Working keys:     {working} / {len(KEYS)}")
print(f"  Total 70B TPD:    {working * TPD_PER_KEY:,} tokens/day")
print(f"  ~P6-size runs/day: {(working * TPD_PER_KEY) // 18_000} "
      f"(est. 18k tokens per 100-row golden gen)")
print("=" * 55)
