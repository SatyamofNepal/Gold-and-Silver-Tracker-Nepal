#!/usr/bin/env python3
"""Fetch recent FENEGOSIDA hallmark-gold and silver rates (NPR per tola) and merge them into prices.json."""
import json, re, sys, urllib.request
from datetime import datetime
from pathlib import Path

SOURCE = "https://kokil.com.np/tools/nepal-gold-silver-price"
FILE = Path(__file__).resolve().parent.parent / "prices.json"
# history rows look like: 17 Nov, 2026 | Rs. 267,200 (hallmark) | Rs. 264,500 (tajabi) | Rs. 3,490 (silver)
ROW = re.compile(r"(\d{1,2} [A-Z][a-z]{2}, \d{4})\s*Rs\.?\s*([\d,]+)\s*Rs\.?\s*([\d,]+)\s*Rs\.?\s*([\d,]+)")

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (personal gold-tracker project)"})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")

def parse(html):
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"[\s|]+", " ", text)
    rows = {}
    for d, gold, _tajabi, silver in ROW.findall(text):
        iso = datetime.strptime(d, "%d %b, %Y").strftime("%Y-%m-%d")
        rows[iso] = [iso, int(gold.replace(",", "")), int(silver.replace(",", ""))]
    return rows

def main():
    new = parse(fetch(SOURCE))
    if not new:
        sys.exit("No rate rows found: the source page layout probably changed.")
    data = json.loads(FILE.read_text())
    have = {r[0]: r for r in data["rates"]}
    last = data["rates"][-1]
    for iso, r in sorted(new.items()):
        if not (50_000 < r[1] < 1_000_000 and 500 < r[2] < 100_000):
            sys.exit(f"Implausible values for {iso}: {r}")
        if iso > last[0] and abs(r[1] / last[1] - 1) > 0.15:
            sys.exit(f"Gold moved more than 15% on {iso}; refusing to write, please check manually.")
        have[iso] = r
    rates = [have[k] for k in sorted(have)]
    if rates == data["rates"]:
        print("No changes.")
        return
    data["rates"], data["updated"] = rates, rates[-1][0]
    body = ",\n".join(json.dumps(r, separators=(",", ":")) for r in rates)
    head = json.dumps({"updated": data["updated"], "source": SOURCE, "rates": "@@"}).replace('"@@"', "[\n" + body + "\n]")
    FILE.write_text(head + "\n")
    print(f"Updated: {len(rates)} rows, latest {rates[-1]}")

if __name__ == "__main__":
    main()
