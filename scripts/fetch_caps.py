import json, os, datetime as dt
import yfinance as yf

OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "history.json")
DATE = dt.date.today().isoformat()

TICKERS = {
    "bp": "BP",        # BP plc (NYSE)
    "coin": "COIN"     # Coinbase Global
}

def get_market_cap(ticker):
    info = yf.Ticker(ticker).fast_info
    # Prefer market_cap if present; fall back to price * shares if available
    mc = getattr(info, "market_cap", None)
    if mc is None:
        price = getattr(info, "last_price", None)
        shares = getattr(info, "shares", None)
        if price and shares:
            mc = float(price) * float(shares)
    return float(mc) if mc else None

bp_mc = get_market_cap(TICKERS["bp"])
coin_mc = get_market_cap(TICKERS["coin"])

if bp_mc is None or coin_mc is None:
    raise SystemExit("Failed to fetch market caps.")

os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
history = []
if os.path.exists(OUT_PATH):
    with open(OUT_PATH, "r") as f:
        history = json.load(f)

# avoid duplicate entry if already added today
if not any(r["date"] == DATE for r in history):
    history.append({
        "date": DATE,
        "bpMarketCap": round(bp_mc),
        "coinMarketCap": round(coin_mc)
    })

with open(OUT_PATH, "w") as f:
    json.dump(history, f, indent=2)
print(f"Added {DATE}: BP={bp_mc:.0f}, COIN={coin_mc:.0f}")
