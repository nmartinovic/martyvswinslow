# scripts/email_report.py
import base64, datetime as dt, io, json, math, os, sys, subprocess
from pathlib import Path
import requests

# Optional chart libs
try:
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except Exception:
    plt = None
    np = None

ROOT = Path(__file__).resolve().parents[1]
HISTORY_PATH = ROOT / "data" / "history.json"
CHART_PATH = ROOT / "images" / "weekly-chart.png"

# --- ENV ---
BREVO_API_KEY   = os.environ.get("BREVO_API_KEY", "")
FROM_EMAIL      = os.environ.get("REPORT_FROM_EMAIL", "")
TO_EMAILS_RAW   = os.environ.get("REPORT_TO_EMAILS", os.environ.get("REPORT_TO_EMAIL", "")).strip()
SITE_URL        = os.environ.get("SITE_URL", "").strip().rstrip("/")  # optional override
GITHUB_REPO     = os.environ.get("GITHUB_REPOSITORY", "")             # owner/repo, provided by Actions

def days_left(end_date=dt.date(2030,5,1)) -> int:
    return max(0, (end_date - dt.date.today()).days)

def money_str(n: float) -> str:
    n = float(n)
    if n >= 1e12: return f"{n/1e12:.2f}T"
    if n >= 1e9:  return f"{n/1e9:.2f}B"
    if n >= 1e6:  return f"{n/1e6:.2f}M"
    return f"{n:,.0f}"

def pct_str(x: float) -> str:
    return f"{x*100:.2f}%"

def clean_rows(history):
    rows = [
        r for r in history
        if r and r.get("date") and r.get("bpMarketCap") is not None and r.get("coinMarketCap") is not None
    ]
    rows.sort(key=lambda r: r["date"])
    return rows

def signed_pct(row) -> float:
    """Signed advantage (%): + = Marty (COIN vs BP denom=BP); − = Winslow (BP vs COIN denom=COIN)."""
    bp = float(row["bpMarketCap"]); coin = float(row["coinMarketCap"])
    diff = coin - bp
    if diff == 0 or bp == 0 or coin == 0: return 0.0
    denom = bp if diff >= 0 else coin
    return diff / denom

def leader_and_ahead(row):
    bp = float(row["bpMarketCap"]); coin = float(row["coinMarketCap"])
    if coin > bp: return "Marty (COIN)", (coin - bp)/bp
    if bp > coin: return "Winslow (BP)", (bp - coin)/coin
    return "Tied", 0.0

def parse_recipients(raw: str):
    parts = [p.strip() for p in raw.replace("\n", ",").replace(" ", ",").split(",") if p.strip()]
    seen, out = set(), []
    for p in parts:
        low = p.lower()
        if low not in seen:
            out.append({"email": p})
            seen.add(low)
    return out

# ---------- Chart ----------
def make_chart_png(rows, save_path: Path):
    if plt is None or np is None:
        raise RuntimeError("matplotlib/numpy not available in environment")
    xs = [dt.date.fromisoformat(r["date"]) for r in rows]
    ys = [signed_pct(r) * 100.0 for r in rows]
    max_abs = max(5.0, math.ceil(max(abs(v) for v in ys) * 1.1))

    import numpy.ma as ma
    y = np.array(ys, dtype=float)
    x = np.array(xs)

    y_pos = ma.masked_less(y, 0.0)     # Marty
    y_neg = ma.masked_greater(y, 0.0)  # Winslow

    fig, ax = plt.subplots(figsize=(11,4))
    ax.axhline(0, color="#cbd5e1", linestyle=(0,(4,3)), linewidth=2)
    ax.fill_between(x, 0, y_pos, where=~y_pos.mask, alpha=0.15, color="#184FF8")
    ax.fill_between(x, 0, y_neg, where=~y_neg.mask, alpha=0.15, color="#007F01")
    ax.plot(x, y_pos, color="#184FF8", linewidth=2)
    ax.plot(x, y_neg, color="#007F01", linewidth=2)

    ax.set_ylim(-max_abs, max_abs)
    ax.set_ylabel("% ahead"); ax.set_xlabel("")
    ax.grid(True, axis="y", linestyle=":", color="#e5e7eb")
    for sp in ("top","right","left","bottom"): ax.spines[sp].set_visible(False)
    fig.tight_layout()

    save_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(save_path, dpi=160)
    plt.close(fig)

def git(*args, check=True):
    return subprocess.run(list(args), check=check, capture_output=True, text=True)

def commit_chart_if_changed():
    subprocess.run(["git","config","user.name","mvw-bot"], check=True)
    subprocess.run(["git","config","user.email","actions@users.noreply.github.com"], check=True)
    subprocess.run(["git","add", str(CHART_PATH)], check=True)
    diff = subprocess.run(["git","diff","--cached","--quiet"])
    if diff.returncode != 0:
        subprocess.run(["git","commit","-m", f"chore(email): update weekly chart {dt.date.today().isoformat()}"], check=True)
        subprocess.run(["git","push"], check=True)

def compute_pages_url() -> str:
    """Prefer explicit SITE_URL (secret/env). Otherwise derive:
       https://<owner>.github.io/<repo>
    """
    if SITE_URL:
        return SITE_URL
    if "/" in GITHUB_REPO:
        owner, repo = GITHUB_REPO.split("/", 1)
        return f"https://{owner}.github.io/{repo}"
    return ""

def build_image_urls() -> list[str]:
    urls = []
    pages = compute_pages_url()
    if pages:
        urls.append(f"{pages}/images/{CHART_PATH.name}")
    # raw.githubusercontent fallback (public repos only)
    if "/" in GITHUB_REPO:
        owner, repo = GITHUB_REPO.split("/", 1)
        # Use the current HEAD ref “main” path; raw with branch works and is stable
        urls.append(f"https://raw.githubusercontent.com/{owner}/{repo}/main/images/{CHART_PATH.name}")
    return [u for u in urls if u]

# ---------- HTML ----------
def html_report(rows, image_urls: list[str]) -> str:
    latest = rows[-1]
    leader, ahead = leader_and_ahead(latest)

    # Δ vs 7d (calendar-based: latest vs most recent row <= latest_date - 7 days)
    latest_date = dt.date.fromisoformat(latest["date"])
    threshold = latest_date - dt.timedelta(days=7)
    idx_old = 0
    for i, r in enumerate(rows):
        d = dt.date.fromisoformat(r["date"])
        if d <= threshold:
            idx_old = i
    delta7 = signed_pct(latest) - signed_pct(rows[idx_old])

    blue, green = "#184FF8", "#007F01"
    leader_color = blue if leader.startswith("Marty") else green

    tail = rows[-7:] if len(rows) >= 7 else rows[:]
    tr_html = []
    for r in reversed(tail):
        nm, pct = leader_and_ahead(r)
        pill = blue if nm.startswith("Marty") else green
        tr_html.append(
            f"<tr>"
            f"<td style='padding:8px;border-bottom:1px solid #e5e7eb'>{r['date']}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e5e7eb'>{money_str(r['bpMarketCap'])}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e5e7eb'>{money_str(r['coinMarketCap'])}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e5e7eb'>{nm}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e5e7eb'>"
            f"<span style='border:1px solid {pill};border-radius:999px;padding:3px 8px;color:{pill};font-size:12px'>{pct_str(pct)}</span>"
            f"</td></tr>"
        )

    # Always include the image tag; many clients block remote images by default,
    # but the PNG is also attached so users can still view it.
    img_tags = "\n".join(
        [f"<img src='{u}' alt='Marty vs Winslow chart' style='width:100%;max-width:1000px;border-radius:12px;display:block;margin:8px 0' />"
         for u in image_urls[:1]]  # use first best URL
    )
    attach_hint = "<div style='color:#6b7280;font-size:12px'>Chart attached as PNG.</div>"

    link_html = ""
    pages = compute_pages_url()
    if pages:
        link_html = (f"<p style='margin:8px 0 0'><a href='{pages}' "
                     f"style='color:#2563eb;text-decoration:none'>Open the live dashboard →</a></p>")

    return f"""<!doctype html>
<html><body style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#0b1221;background:#ffffff;margin:0;padding:16px;">
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
            <div style="font-weight:800;font-size:22px;color:{leader_color}">{leader}</div>
          </td>
          <td style="padding:6px 0;width:33%;">
            <div style="color:#6b7280;font-size:13px;">% ahead</div>
            <div style="font-weight:700;font-size:22px;">{pct_str(ahead)} <span style="color:#6b7280;font-size:12px">(Δ vs 7d: {pct_str(delta7)})</span></div>
          </td>
        </tr>
      </table>
      <div style="color:#6b7280;font-size:12px;margin-top:4px">% ahead = (leader − loser) / loser</div>
    </div>

    {img_tags}
    {attach_hint}

    <div style="background:#f8fafc;border-radius:12px;padding:14px 16px;margin-top:12px;">
      <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px;">
        <strong>Last 7 entries</strong>
        <span style="color:#6b7280;font-size:12px;">Updated {rows[-1]['date']}</span>
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

    <div style="color:#6b7280;font-size:12px;margin-top:12px;">This email was sent automatically by GitHub Actions using Brevo.</div>
  </div>
</body></html>"""

def send_email_with_brevo(html, attachments):
    if not BREVO_API_KEY: raise RuntimeError("BREVO_API_KEY missing")
    to_list = parse_recipients(TO_EMAILS_RAW)
    if not to_list: raise RuntimeError("REPORT_TO_EMAIL(S) missing")

    payload = {
        "sender": {"email": FROM_EMAIL or "no-reply@example.com", "name": "Marty vs Winslow"},
        "to": to_list,
        "subject": f"Marty vs Winslow — Weekly Update ({dt.date.today().isoformat()})",
        "htmlContent": html
    }
    if attachments:
        payload["attachment"] = attachments  # [{"name":"weekly-chart.png","content":"<base64>"}]

    r = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={"accept":"application/json","content-type":"application/json","api-key":BREVO_API_KEY},
        json=payload, timeout=45
    )
    if r.status_code not in (200,201,202):
        print("Brevo error:", r.status_code, r.text)
        r.raise_for_status()
    print("Brevo accepted:", r.text[:300])

def main():
    # Load history
    with open(HISTORY_PATH, "r", encoding="utf-8") as f:
        history = json.load(f)
    rows = clean_rows(history)
    if not rows: raise SystemExit("No data rows")

    # Make chart PNG & commit (so Pages/raw can serve it)
    make_chart_png(rows, CHART_PATH)
    commit_chart_if_changed()

    # Build one or more public URLs
    image_urls = build_image_urls()

    # Attach PNG (works even if remote images blocked)
    with open(CHART_PATH, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    attachments = [{"name": CHART_PATH.name, "content": b64}]

    html = html_report(rows, image_urls)
    send_email_with_brevo(html, attachments)

if __name__ == "__main__":
    main()
