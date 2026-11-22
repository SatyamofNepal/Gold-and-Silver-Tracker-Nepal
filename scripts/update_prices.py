#!/usr/bin/env python3
"""Update prices.json with the latest FENEGOSIDA hallmark-gold and silver rates (NPR per tola).

Main source: FENEGOSIDA's own website feed (official, published about 10:30 AM Nepal time).
Backup source: the history table on kokil.com.np (used only if the official feed fails).
"""
import json, re, sys, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

OFFICIAL = "https://api.fenegosida.org/api/website/v1/Dashboard/today"
BACKUP = "https://kokil.com.np/tools/nepal-gold-silver-price"
FILE = Path(__file__).resolve().parent.parent / "prices.json"
TOLA = 11.6638
NPT = timezone(timedelta(hours=5, minutes=45))  # Nepal time
BACKUP_ROW = re.compile(r"(\d{1,2} [A-Z][a-z]{2}, \d{4})\s*Rs\.?\s*([\d,]+)\s*Rs\.?\s*([\d,]+)\s*Rs\.?\s*([\d,]+)")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (personal gold-tracker project)"})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")


def nepal_date(stamp):
    """'2026-11-22T04:40:57.637+00:00' -> '2026-11-22' (the date in Nepal)."""
    return datetime.fromisoformat(stamp).astimezone(NPT).strftime("%Y-%m-%d")


def parse_official(text):
    """Read FENEGOSIDA's feed. Returns {date: [date, gold_per_tola, silver_per_tola]} for today and the previous rate."""
    found = {}
    for item in json.loads(text):
        name = item.get("rateType", "")
        if "छापावाल" in name:
            metal = "gold"          # hallmark gold
        elif "चाँदी" in name or "चांदी" in name:
            metal = "silver"        # pure silver
        else:
            continue                # other types (e.g. tejabi) are ignored
        unit = "tola" if "तोला" in name else "10g" if "ग्राम" in name else None
        if unit:
            found[(metal, unit)] = item
    gold, silver = found.get(("gold", "tola")), found.get(("silver", "tola"))
    if not gold or not silver:
        raise ValueError("gold or silver per-tola row not found in the feed")
    # Cross-check: the 10 gram rate must agree with the tola rate.
    for metal in ("gold", "silver"):
        tola, ten = found[(metal, "tola")], found.get((metal, "10g"))
        if ten:
            for key in ("todayBaseRatePerGram", "yestardayBaseRatePerGram"):
                expected = tola[key] * 10 / TOLA
                if abs(expected - ten[key]) / ten[key] > 0.005:
                    raise ValueError(f"{metal}: 10 g rate does not match tola rate ({ten[key]} vs {expected:.0f})")
    rows = {}
    for date_key, value_key in (("todayDate", "todayBaseRatePerGram"), ("yestardayDate", "yestardayBaseRatePerGram")):
        d_gold, d_silver = nepal_date(gold[date_key]), nepal_date(silver[date_key])
        if d_gold != d_silver:
            raise ValueError("gold and silver dates differ in the feed")
        rows[d_gold] = [d_gold, int(round(gold[value_key])), int(round(silver[value_key]))]
    return rows


def parse_backup(html):
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"[\s|]+", " ", text)
    rows = {}
    for d, gold, _tajabi, silver in BACKUP_ROW.findall(text):
        iso = datetime.strptime(d, "%d %b, %Y").strftime("%Y-%m-%d")
        rows[iso] = [iso, int(gold.replace(",", "")), int(silver.replace(",", ""))]
    if not rows:
        raise ValueError("no rate rows found: the page layout probably changed")
    return rows


def check(rows, last):
    for iso, r in sorted(rows.items()):
        if not (50_000 < r[1] < 1_000_000 and 500 < r[2] < 100_000):
            raise ValueError(f"implausible values for {iso}: {r}")
        if iso > last[0] and abs(r[1] / last[1] - 1) > 0.15:
            raise ValueError(f"gold moved more than 15% on {iso}; refusing to save, please check manually")


def main():
    data = json.loads(FILE.read_text())
    last = data["rates"][-1]
    rows, used, errors = None, None, []
    for name, url, parse in (("FENEGOSIDA official feed", OFFICIAL, parse_official), ("kokil backup", BACKUP, parse_backup)):
        try:
            rows = parse(fetch(url))
            check(rows, last)
            used = url
            print(f"Using {name}: {len(rows)} rows, newest {max(rows)}")
            break
        except Exception as e:
            rows = None
            errors.append(f"{name}: {e}")
            print(f"::warning::{name} failed: {e}")
    if rows is None:
        sys.exit("All sources failed. " + " | ".join(errors))
    have = {r[0]: r for r in data["rates"]}
    for iso, r in rows.items():
        have[iso] = r
    rates = [have[k] for k in sorted(have)]
    if rates == data["rates"]:
        print("No changes.")
        return
    data["rates"], data["updated"], data["source"] = rates, rates[-1][0], used
    body = ",\n".join(json.dumps(r, separators=(",", ":")) for r in rates)
    head = json.dumps({"updated": data["updated"], "source": used, "rates": "@@"}).replace('"@@"', "[\n" + body + "\n]")
    FILE.write_text(head + "\n")
    print(f"Updated: {len(rates)} rows, latest {rates[-1]}")


if __name__ == "__main__":
    main()
