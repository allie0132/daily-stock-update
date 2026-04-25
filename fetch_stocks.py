import json
import os
import urllib.request
from datetime import date
import yfinance as yf

with open("config.json") as f:
    config = json.load(f)

tickers = config["tickers"]
today = date.today().isoformat()
report_dir = "daily-reports"
os.makedirs(report_dir, exist_ok=True)

stocks = []
for ticker in tickers:
    try:
        t = yf.Ticker(ticker)
        fast = t.fast_info
        info = t.info
        hist = t.history(period="1mo")

        price = fast.last_price
        prev = fast.previous_close
        change = price - prev
        pct = (change / prev) * 100

        # 1-month trend
        if len(hist) >= 2:
            month_start = hist["Close"].iloc[0]
            month_pct = (price - month_start) / month_start * 100
        else:
            month_pct = None

        # Analyst target price
        target = info.get("targetMeanPrice")
        target_high = info.get("targetHighPrice")
        target_low = info.get("targetLowPrice")
        upside = ((target - price) / price * 100) if target else None
        recommendation = info.get("recommendationKey", "").replace("_", " ").title()

        stocks.append({
            "ticker": ticker,
            "price": price,
            "change": change,
            "pct": pct,
            "month_pct": month_pct,
            "target": target,
            "target_high": target_high,
            "target_low": target_low,
            "upside": upside,
            "recommendation": recommendation,
        })
    except Exception as e:
        print(f"Warning: failed to fetch {ticker}: {e}")
        stocks.append({
            "ticker": ticker, "price": None, "change": None, "pct": None,
            "month_pct": None, "target": None, "target_high": None,
            "target_low": None, "upside": None, "recommendation": None,
        })

# Markdown report
md_lines = [f"# Stock Report — {today}\n"]
for s in stocks:
    if s["price"] is None:
        md_lines.append(f"- **{s['ticker']}**: unavailable")
    else:
        arrow = "▲" if s["change"] >= 0 else "▼"
        line = f"- **{s['ticker']}**: ${s['price']:.2f} {arrow} {s['pct']:+.2f}%"
        if s["month_pct"] is not None:
            line += f" | 1M: {s['month_pct']:+.2f}%"
        if s["target"]:
            line += f" | Target: ${s['target']:.2f} ({s['upside']:+.1f}%)"
        if s["recommendation"]:
            line += f" | {s['recommendation']}"
        md_lines.append(line)

md_path = os.path.join(report_dir, f"{today}.md")
with open(md_path, "w") as f:
    f.write("\n".join(md_lines) + "\n")

# HTML report
def trend_badge(pct):
    if pct is None:
        return '<span class="na">—</span>'
    color = "#16a34a" if pct >= 0 else "#dc2626"
    return f'<span style="color:{color}">{pct:+.2f}%</span>'

def row_html(s):
    if s["price"] is None:
        return f'<tr><td class="ticker">{s["ticker"]}</td><td colspan="6" class="na">unavailable</td></tr>'
    color = "#16a34a" if s["change"] >= 0 else "#dc2626"
    arrow = "▲" if s["change"] >= 0 else "▼"
    target_cell = f'${s["target"]:.2f}' if s["target"] else '<span class="na">—</span>'
    upside_cell = trend_badge(s["upside"])
    rec = s["recommendation"] or "—"
    rec_color = {"Buy": "#16a34a", "Strong Buy": "#15803d", "Hold": "#d97706",
                 "Sell": "#dc2626", "Underperform": "#dc2626"}.get(rec, "#6b7280")
    return (
        f'<tr>'
        f'<td class="ticker">{s["ticker"]}</td>'
        f'<td class="price">${s["price"]:.2f}</td>'
        f'<td style="color:{color}">{arrow} {s["pct"]:+.2f}%</td>'
        f'<td>{trend_badge(s["month_pct"])}</td>'
        f'<td>{target_cell}</td>'
        f'<td>{upside_cell}</td>'
        f'<td style="color:{rec_color};font-size:0.8rem">{rec}</td>'
        f'</tr>'
    )

rows = "\n".join(row_html(s) for s in stocks)
html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Stock Report — {today}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         max-width: 680px; margin: 40px auto; padding: 0 16px; background: #0f172a; color: #e2e8f0; }}
  h1 {{ font-size: 1.2rem; color: #94a3b8; margin-bottom: 4px; }}
  p.date {{ color: #475569; font-size: 0.85rem; margin: 0 0 20px; }}
  table {{ width: 100%; border-collapse: collapse; background: #1e293b;
           border-radius: 10px; overflow: hidden;
           box-shadow: 0 1px 8px rgba(0,0,0,0.4); }}
  th {{ background: #0f172a; color: #64748b; padding: 10px 12px; text-align: left; font-size: 0.75rem; white-space: nowrap; letter-spacing: 0.05em; text-transform: uppercase; }}
  td {{ padding: 11px 12px; border-bottom: 1px solid #0f172a; font-size: 0.9rem; white-space: nowrap; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: #273449; }}
  .ticker {{ font-weight: 700; letter-spacing: 0.03em; color: #f1f5f9; }}
  .price {{ font-weight: 600; color: #f1f5f9; }}
  .na {{ color: #475569; font-style: italic; }}
</style>
</head>
<body>
<h1>Daily Stock Report</h1>
<p class="date">{today}</p>
<table>
<thead><tr>
  <th>Ticker</th><th>Price</th><th>Day</th><th>1 Month</th>
  <th>Target</th><th>Upside</th><th>Rating</th>
</tr></thead>
<tbody>
{rows}
</tbody>
</table>
</body>
</html>"""

html_path = os.path.join(report_dir, f"{today}.html")
with open(html_path, "w") as f:
    f.write(html)

# index.html redirect
index = f"""<!DOCTYPE html>
<html><head><meta http-equiv="refresh" content="0;url=daily-reports/{today}.html">
<title>Redirecting...</title></head>
<body>Redirecting to <a href="daily-reports/{today}.html">today's report</a>.</body></html>"""

with open("index.html", "w") as f:
    f.write(index)

print(f"Reports saved: {md_path}, {html_path}")

# Telegram notification
tg_token = os.environ.get("TELEGRAM_TOKEN")
tg_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
if tg_token and tg_chat_id:
    lines = [f"📈 *Stock Report — {today}*\n"]
    for s in stocks:
        if s["price"] is None:
            lines.append(f"• *{s['ticker']}*: unavailable")
        else:
            arrow = "🟢" if s["change"] >= 0 else "🔴"
            line = f"{arrow} *{s['ticker']}*: ${s['price']:.2f} ({s['pct']:+.2f}%)"
            if s["month_pct"] is not None:
                line += f" | 1M: {s['month_pct']:+.2f}%"
            if s["target"]:
                line += f" | 🎯 ${s['target']:.2f} ({s['upside']:+.1f}%)"
            lines.append(line)
    lines.append(f"\n[Full report](https://allie0132.github.io/daily-stock-update/)")
    msg = "\n".join(lines)
    payload = json.dumps({"chat_id": tg_chat_id, "text": msg, "parse_mode": "Markdown"}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{tg_token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(req)
        print("Telegram notification sent.")
    except Exception as e:
        print(f"Telegram notification failed: {e}")
