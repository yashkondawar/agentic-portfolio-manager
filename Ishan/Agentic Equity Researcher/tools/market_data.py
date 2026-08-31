"""Deterministic market data pull (yfinance). Never ask an LLM for what this script provides.

Usage:
  python tools/market_data.py TICKER.NS --out workspace/TICKER/facts/market_data.json
      [--index ^NSEI] [--sector-index ^CNXPHARMA] [--years 12]

Outputs fact records (schema/fact_record.schema.json shapes) for:
  - FY-average price, FY-end price, FY price return (Indian FY: Apr 1 - Mar 31)
  - current price, market cap, shares outstanding, 52w high/low
  - cycle signals: euphoria (1y >= +100%), panic (1y <= -40% or 5y CAGR <= -10%),
    neglect (>=10y total return within +/-10%)
  - same return set for the market index and sector index (context for cycle positioning)
All records carry src 'yfinance' with pull timestamp. Exit code 2 on network failure so the
orchestrator can route a fallback instead of silently proceeding.
"""
import argparse, json, sys, datetime as dt
from pathlib import Path


def fy_label(date) -> str:
    # FY2024 = 2023-04-01 .. 2024-03-31
    return f"FY{date.year + 1}" if date.month >= 4 else f"FY{date.year}"


def fy_series(closes):
    """closes: pandas Series indexed by date -> dict fy -> {avg, end, start}"""
    buckets = {}
    for date, px in closes.items():
        fy = fy_label(date)
        b = buckets.setdefault(fy, {"sum": 0.0, "n": 0, "first": None, "last": None})
        b["sum"] += float(px); b["n"] += 1
        if b["first"] is None:
            b["first"] = float(px)
        b["last"] = float(px)
    out = {}
    for fy, b in buckets.items():
        out[fy] = {"avg": b["sum"] / b["n"], "end": b["last"], "start": b["first"], "days": b["n"]}
    return out


def pct(a, b):
    return None if (a is None or b in (None, 0)) else (a / b - 1.0) * 100.0


def pull(symbol, years):
    import yfinance as yf
    t = yf.Ticker(symbol)
    hist = t.history(period=f"{years}y", interval="1d", auto_adjust=True)
    if hist is None or len(hist) == 0:
        raise RuntimeError(f"no price history returned for {symbol}")
    closes = hist["Close"].dropna()
    info = {}
    try:
        fi = t.fast_info
        info = {"last_price": getattr(fi, "last_price", None),
                "market_cap": getattr(fi, "market_cap", None),
                "shares": getattr(fi, "shares", None),
                "year_high": getattr(fi, "year_high", None),
                "year_low": getattr(fi, "year_low", None),
                "currency": getattr(fi, "currency", None)}
    except Exception:
        pass
    return closes, info


def returns_block(closes):
    last = float(closes.iloc[-1]); last_date = closes.index[-1]
    out = {"last": last, "last_date": str(last_date.date())}

    def back(years_back):
        target = last_date - dt.timedelta(days=int(365.25 * years_back))
        prior = closes[closes.index <= target]
        return (float(prior.iloc[-1]), prior.index[-1]) if len(prior) else (None, None)

    for y in (1, 3, 5, 10, 12):
        px, d = back(y)
        out[f"abs_return_{y}y_pct"] = pct(last, px)
        if px and y >= 3:
            out[f"cagr_{y}y_pct"] = ((last / px) ** (1.0 / y) - 1.0) * 100.0
    return out


def signals(rb):
    sig = {}
    r1, r5c = rb.get("abs_return_1y_pct"), rb.get("cagr_5y_pct")
    r10, r12 = rb.get("abs_return_10y_pct"), rb.get("abs_return_12y_pct")
    sig["euphoria_avoid"] = bool(r1 is not None and r1 >= 100.0)
    sig["panic_buy"] = bool((r1 is not None and r1 <= -40.0) or (r5c is not None and r5c <= -10.0))
    longest = r12 if r12 is not None else r10
    sig["neglect_long_term"] = bool(longest is not None and abs(longest) <= 10.0)
    return sig


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    ap.add_argument("--out", required=True)
    ap.add_argument("--index", default="^NSEI")
    ap.add_argument("--sector-index", default=None)
    ap.add_argument("--years", type=int, default=12)
    a = ap.parse_args()

    pulled_at = dt.datetime.now().isoformat(timespec="seconds")
    src = {"doc": "yfinance", "kind": "market_data", "page": None,
           "locator": a.ticker, "accessed": pulled_at, "url": None}
    facts, errors = [], []

    def add(metric, value, unit, period, extra=None):
        rec = {"id": f"F-MKT-{metric.upper()}-{period}", "metric": metric, "label": metric,
               "value": value, "unit": unit, "period": period,
               "period_type": "FY" if period.startswith("FY") else "POINT",
               "basis": "na", "level": 1, "parent": None,
               "source": {"src_id": "SRC-MKT-001", "quote": None},
               "method": "reported", "formula": None, "inputs": [],
               "confidence": "high", "load_bearing": False, "flags": []}
        if extra:
            rec.update(extra)
        facts.append(rec)

    try:
        closes, info = pull(a.ticker, a.years)
    except Exception as e:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps({"error": str(e), "ticker": a.ticker,
                                           "pulled_at": pulled_at}, indent=2), encoding="utf-8")
        print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(2)

    fys = fy_series(closes)
    fy_keys = sorted(fys)
    for i, fy in enumerate(fy_keys):
        b = fys[fy]
        partial = b["days"] < 200  # partial FY (current year or data start)
        fl = ["partial_fy"] if partial else []
        add("fy_avg_price", round(b["avg"], 2), "INR", fy, {"flags": fl})
        add("fy_end_price", round(b["end"], 2), "INR", fy, {"flags": fl})
        if i > 0:
            prev = fys[fy_keys[i - 1]]
            add("fy_price_return", round(pct(b["end"], prev["end"]), 2), "pct", fy, {"flags": fl})

    rb = returns_block(closes)
    now = "POINT" + rb["last_date"]
    add("current_price", round(rb["last"], 2), "INR", now)
    for k, v in rb.items():
        if k.endswith("_pct") and v is not None:
            add(k, round(v, 2), "pct", now)
    for k, v in signals(rb).items():
        add(f"signal_{k}", v, "bool", now)
    if info.get("market_cap"):
        add("market_cap", round(info["market_cap"] / 1e7, 1), "INR_cr", now)  # 1 cr = 1e7
    if info.get("shares"):
        add("shares_outstanding", round(info["shares"] / 1e7, 4), "cr_shares", now)
    for k_src, k_dst in (("year_high", "week52_high"), ("year_low", "week52_low")):
        if info.get(k_src):
            add(k_dst, round(float(info[k_src]), 2), "INR", now)

    indices = {}
    for label, sym in (("market_index", a.index), ("sector_index", a.sector_index)):
        if not sym:
            continue
        try:
            icloses, _ = pull(sym, a.years)
            irb = returns_block(icloses)
            indices[label] = {"symbol": sym, "returns": {k: (round(v, 2) if isinstance(v, float) else v)
                                                         for k, v in irb.items()},
                              "signals": signals(irb)}
        except Exception as e:
            errors.append(f"{label} {sym}: {e}")

    out = {"ticker": a.ticker, "pulled_at": pulled_at, "source_registry_entry": {"SRC-MKT-001": src},
           "facts": facts, "indices": indices, "errors": errors}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"OK: {len(facts)} facts, {len(indices)} indices -> {a.out}"
          + (f" (warnings: {errors})" if errors else ""))


if __name__ == "__main__":
    main()
