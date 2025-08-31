# Marty vs Winslow

A tiny, zero-maintenance site and weekly email that track a friendly bet:

> **If Coinbase (COIN) has a higher market cap than BP on _May 1, 2030_, Marty wins.  
> If BP has a higher market cap than COIN, Winslow wins.**

- **Live site:** GitHub Pages (mobile-first)
- **Data source:** Daily market caps via GitHub Actions + `yfinance`
- **Email:** Weekly Wednesday email via Brevo (chart included)

---

## What the site shows

- **Days left** to May 1, 2030
- **Currently winning** (Marty/COIN or Winslow/BP)
- **% ahead** — defined as **(leader − loser) / loser**
- A **zero-centered chart** of the **signed advantage** over time  
  (blue above 0 for Marty, green below 0 for Winslow)
- A compact **history table**

---

## Repo structure
├── index.html # Frontend (Chart.js, mobile-first)
├── data/
│ └── history.json # Daily snapshot [{date, bpMarketCap, coinMarketCap}, ...]
├── images/
│ └── weekly-chart.png # Auto-generated for the weekly email
├── scripts/
│ ├── fetch_caps.py # Daily updater: writes data/history.json (via yfinance)
│ └── email_report.py # Generates chart + sends Brevo email (Wednesdays)
└── .github/workflows/
├── daily.yml # Runs fetch_caps.py once per day after market close
└── weekly-email.yml # Sends weekly email with inline chart


---

## How it works

### 1) Daily data update
- **Workflow:** `.github/workflows/daily.yml`
- **What it does:** Runs `scripts/fetch_caps.py` to fetch COIN and BP market caps and append a row to `data/history.json` (one row per day).
- **Why JSON:** The site stays static and keeps working even if APIs fail; you can inspect history in Git.

### 2) Website
- **File:** `index.html`
- **Chart logic:** builds a signed series (percent), inserts zero-crossing points, then renders two datasets:
  - **Blue** (`#184FF8`) for `y ≥ 0` (Marty leads)
  - **Green** (`#007F01`) for `y ≤ 0` (Winslow leads)
  - Fill is transparent to the zero baseline.
- **Percent ahead:** `(leader − loser) / loser` (matches the KPIs and email)

### 3) Weekly email (Brevo)
- **Workflow:** `.github/workflows/weekly-email.yml`
- **Script:** `scripts/email_report.py`
- **What it does:** Generates `images/weekly-chart.png`, commits it, and emails a compact HTML report **with the chart embedded** (no attachment).

---

## Setup

1. **Enable GitHub Pages**
   - Settings → Pages → *Deploy from a branch* → Branch: `main` → `/ (root)`
   - The default URL will be `https://<owner>.github.io/<repo>`  
     (If the repo is named `<owner>.github.io`, the site lives at `https://<owner>.github.io`.)

2. **Secrets (GitHub → Settings → Secrets and variables → Actions)**  
   Create:
   - `BREVO_API_KEY` — Brevo **Transactional API** key (starts with `xkeysib-`)
   - `REPORT_FROM_EMAIL` — a **verified sender** in Brevo
   - `REPORT_TO_EMAILS` — one or more recipients, comma/newline separated  
     e.g. `nick@example.com, friend1@example.com` on separate lines is fine
   - *(optional)* `SITE_URL` — set to your Pages URL if you want to override auto-detection

3. **Brevo security (Authorized IPs)**
   - If you enable “Authorized IPs” in Brevo, GitHub-hosted runners will be blocked.
     - Easiest: disable IP restriction (API key remains the guard).
     - Or: run a **self-hosted runner** with a static IP and allowlist it in Brevo.

4. **Trigger the workflows**
   - Daily updater runs on schedule; you can also run it from **Actions → daily.yml → Run workflow**.
   - Weekly email runs each Wednesday (02:00 UTC). Use **workflow_dispatch** to test immediately.

---

## Customization

- **Colors**  
  - Marty: `#184FF8` (blue)  
  - Winslow: `#007F01` (green)  
  Update in `index.html` (CSS variables) and the chart code inside `email_report.py`.

- **Update time**  
  - Daily job cron (after market close): `.github/workflows/daily.yml`
  - Weekly email cron (Wednesdays): `.github/workflows/weekly-email.yml`

- **Recipients**  
  Add/remove emails in the `REPORT_TO_EMAILS` secret; supports commas or newlines.

---

## Troubleshooting

- **Email shows no chart**  
  - Ensure GitHub Pages is enabled and public.  
  - Confirm `images/weekly-chart.png` exists in the repo (the email workflow commits it each run).  
  - Some email apps block remote images by default; the message still includes a link to the live dashboard.

- **Brevo 401 Unauthorized**  
  - Likely due to “Authorized IPs”. Disable it or send from a static IP (self-hosted runner).
  - Confirm you’re using an **API key**, not SMTP password.

- **Chart blank on the website**  
  - Check that `data/history.json` has valid numeric values and dates sorted (the site sorts on load).
  - Open DevTools Console for any errors.

- **`yfinance` errors**  
  - Temporary rate limits: the last known JSON still renders. The workflow tries again the next day.

---

## License
Personal use. Feel free to fork and adapt.


