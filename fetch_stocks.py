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
        info = yf.Ticker(ticker).fast_info
        price = info.last_price
        prev = info.previous_close
        change = price - prev
        pct = (change / prev) * 100
        stocks.append({"ticker": ticker, "price": price, "change": change, "pct": pct})
    except Exception as e:
        print(f"Warning: failed to fetch {ticker}: {e}")
        stocks.append({"ticker": ticker, "price": None, "change": None, "pct": None})

# Markdown report
md_lines = [f"# Stock Report — {today}\n"]
for s in stocks:
    if s["price"] is None:
        md_lines.append(f"- **{s['ticker']}**: unavailable")
    else:
        arrow = "▲" if s["change"] >= 0 else "▼"
        md_lines.append(f"- **{s['ticker']}**: ${s['price']:.2f}  {arrow} {s['pct']:+.2f}%")

md_path = os.path.join(report_dir, f"{today}.md")
with open(md_path, "w") as f:
    f.write("\n".join(md_lines) + "\n")

# HTML report
def row_html(s):
    if s["price"] is None:
        return f'<tr><td class="ticker">{s["ticker"]}</td><td colspan="3" class="na">unavailable</td></tr>'
    color = "#16a34a" if s["change"] >= 0 else "#dc2626"
    arrow = "▲" if s["change"] >= 0 else "▼"
    return (
        f'<tr>'
        f'<td class="ticker">{s["ticker"]}</td>'
        f'<td class="price">${s["price"]:.2f}</td>'
        f'<td style="color:{color}">{arrow} ${abs(s["change"]):.2f}</td>'
        f'<td style="color:{color}">{s["pct"]:+.2f}%</td>'
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
         max-width: 480px; margin: 40px auto; padding: 0 16px; background: #f9fafb; color: #111; }}
  h1 {{ font-size: 1.2rem; color: #374151; margin-bottom: 4px; }}
  p.date {{ color: #6b7280; font-size: 0.85rem; margin: 0 0 20px; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff;
           border-radius: 10px; overflow: hidden;
           box-shadow: 0 1px 4px rgba(0,0,0,0.08); }}
  th {{ background: #1e293b; color: #fff; padding: 10px 14px; text-align: left; font-size: 0.8rem; }}
  td {{ padding: 12px 14px; border-bottom: 1px solid #f1f5f9; font-size: 0.95rem; }}
  tr:last-child td {{ border-bottom: none; }}
  .ticker {{ font-weight: 700; letter-spacing: 0.03em; }}
  .price {{ font-weight: 600; }}
  .na {{ color: #9ca3af; font-style: italic; }}
</style>
</head>
<body>
<h1>Daily Stock Report</h1>
<p class="date">{today}</p>
<table>
<thead><tr><th>Ticker</th><th>Price</th><th>Change</th><th>%</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
</body>
</html>"""

html_path = os.path.join(report_dir, f"{today}.html")
with open(html_path, "w") as f:
    f.write(html)

# index.html redirect to today's report
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
            lines.append(f"{arrow} *{s['ticker']}*: ${s['price']:.2f} ({s['pct']:+.2f}%)")
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
