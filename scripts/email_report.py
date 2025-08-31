# scripts/email_report.py
import json, os, datetime as dt, math, sys
import requests
from pathlib import Path

# --- Config via env ---
BREVO_API_KEY    = os.environ["BREVO_API_KEY"]
TO_EMAIL         = os.environ["REPORT_TO_EMAIL"]
FROM_EMAIL       = os.environ["REPORT_FROM_EMAIL"]   # must be a verified Brevo sender
SITE_URL         = os.environ.get("SITE_URL", "")    # e.g. https://<user>.github.io/<repo>

ROOT = Path(__file__).resolve().parents[1]
HISTORY_PATH = ROOT / "data" / "history.json"

def pct_str(x):
    return f"{x*100:.2f}%"

def money_str(n):
    n = float(n)
    if n >= 1e12: return f"{n/1e12:.2f}T"
    if n >= 1e9:  return f"{n/1e9:.2f}B"
    if n >= 1e6:  return f"{n/1e6:.2f}M"
    return f"{n:,.0f}"

def leader_and_ahead(bp, coin):
    bp = float(bp); coin = float(coin)
    if coin > bp:    return "Marty (COIN)", (coin - bp)/bp
    if bp > coin:    return "Winslow (BP)", (bp - coin)/coin
    return "Tied", 0.0

def days_left(end_date=dt.date(2030,5,1)):
    today = dt.date.today()
    return max(0, (end_date - today).days)

def build_rows(history):
    # keep only valid rows & sort by date asc
    rows = [r for r in history if r.get("date") and r.get("bpMarketCap") and r.get("coinMarketCap")]
    rows.sort(key=lambda r: r["date"])
    return rows

def last_n(rows, n):
    return rows[-n:] if len(rows) >= n else rows

def html_report(rows):
    if not rows:
        return "<p>No data yet.</p>"

    latest = rows[-1]
    bp = latest["bpMarketCap"]; coin = latest["coinMarketCap"]
    leader, ahead = leader_and_ahead(bp, coin)

    # 7-day slice (or less if not available)
    slice7 = last_n(rows, 7)
    # simple textual trend (+/- vs 7 days ago)
    trend_txt = ""
    if len(slice7) >= 2:
        old_leader, old_ahead = leader_and_ahead(slice7[0]["bpMarketCap"], slice7[0]["coinMarketCap"])
        delta = ahead - old_ahead if leader != "Tied" else 0
        trend_txt = f" (Δ vs 7d: {pct_str(delta)})"

    blue = "#184FF8"   # Marty
    green = "#007F01"  # Winslow

    def leader_color(name):
        return blue if name.startswith("Marty") else green

    # Build table rows (newest first)
    tr_html = []
    for r in reversed(slice7):
        nm, pct = leader_and_ahead(r["bpMarketCap"], r["coinMarketCap"])
        pill_color = leader_color(nm)
        tr_html.append(
            f"<tr>"
            f"<td style='padding:8px;border-bottom:1px solid #e5e7eb'>{r['date']}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e5e7eb'>{money_str(r['bpMarketCap'])}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e5e7eb'>{money_str(r['coinMarketCap'])}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e5e7eb'>{nm}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e5e7eb'>"
            f"<span style='border:1px solid {pill_color};border-radius:999px;padding:3px 8px;color:{pill_color};font-size:12px'>{pct_str(pct)}</span>"
            f"</td></tr>"
        )

    link_html = f"<p style='margin:12px 0 0'><a href='{SITE_URL}' style='color:#2563eb;text-decoration:none'>Open the live dashboard →</a></p>" if SITE_URL else ""

    html = f"""
<!doctype html>
<html>
  <body style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#0b1221;background:#ffffff;margin:0;padding:16px;">
    <div style="max-width:720px;margin:0 auto;">
      <h2 style="margin:0 0 4px 0;">Marty vs Winslow — Weekly Update</h2>
      <div style="color:#6b7280;margin-bottom:12px;">COIN vs BP market capitalization • Ends May 1, 2030</div>

      <div style="background:#f8fafc;border-radius:12px;padding:14px 16px;margin-bottom:12px;">
        <table role="presentation" style="width:100%;border-collapse:collapse">
          <tr>
            <td style="padding:6px 0;width:33%;">
              <div style="color:#6b7280;font-size:13px;">Days left</div>
              <div style="font-weight:700;font-size:22px;">{days_left()}</div>
            </td>
            <td style="padding:6px 0;width:33%;">
              <div style="color:#6b7280;font-size:13px;">Currently winning</div>
              <div style="font-weight:800;font-size:22px;color:{leader_color(leader)}">{leader}</div>
            </td>
            <td style="padding:6px 0;width:33%;">
              <div style="color:#6b7280;font-size:13px;">% ahead</div>
              <div style="font-weight:700;font-size:22px;">{pct_str(ahead)}{trend_txt}</div>
            </td>
          </tr>
        </table>
        <div style="color:#6b7280;font-size:12px;margin-top:4px">% ahead = (leader − loser) / loser</div>
      </div>

      <div style="background:#f8fafc;border-radius:12px;padding:14px 16px;">
        <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px;">
          <strong>Last 7 entries</strong>
          <span style="color:#6b7280;font-size:12px;">Updated {latest['date']}</span>
        </div>
        <table style="width:100%;border-collapse:collapse;">
          <thead>
            <tr>
              <th align="left" style="padding:8px;border-bottom:1px solid #e5e7eb;">Date</th>
              <th align="left" style="padding:8px;border-bottom:1px solid #e5e7eb;">BP Market Cap</th>
              <th align="left" style="padding:8px;border-bottom:1px solid #e5e7eb;">COIN Market Cap</th>
              <th align="left" style="padding:8px;border-bottom:1px solid #e5e7eb;">Leader</th>
              <th align="left" style="padding:8px;border-bottom:1px solid #e5e7eb;">% Ahead</th>
            </tr>
          </thead>
          <tbody>
            {''.join(tr_html)}
          </tbody>
        </table>
        {link_html}
      </div>

      <div style="color:#6b7280;font-size:12px;margin-top:12px;">
        This email was sent automatically by GitHub Actions using Brevo.
      </div>
    </div>
  </body>
</html>
"""
    return html

def send_email(html):
    today = dt.date.today().isoformat()
    payload = {
        "sender": {"email": FROM_EMAIL, "name": "Marty vs Winslow"},
        "to": [{"email": TO_EMAIL}],
        "subject": f"Marty vs Winslow — Weekly Update ({today})",
        "htmlContent": html
    }
    r = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={"accept":"application/json","content-type":"application/json","api-key":BREVO_API_KEY},
        json=payload, timeout=30
    )
    r.raise_for_status()
    print("Brevo accepted message:", r.json())

def main():
    if not HISTORY_PATH.exists():
        print("No history.json found at", HISTORY_PATH, file=sys.stderr)
        sys.exit(1)
    with open(HISTORY_PATH, "r", encoding="utf-8") as f:
        history = json.load(f)

    rows = build_rows(history)
    html = html_report(rows)
    send_email(html)

if __name__ == "__main__":
    main()
