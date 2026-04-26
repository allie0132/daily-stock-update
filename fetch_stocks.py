import json
import os
import urllib.request
from datetime import date, datetime
from zoneinfo import ZoneInfo
import yfinance as yf

with open("config.json") as f:
    config = json.load(f)

tickers = config["tickers"]
today = date.today().isoformat()
now_et = datetime.now(ZoneInfo("America/New_York"))
date_str = now_et.strftime("%A, %b %d %Y · %I:%M %p ET")
report_dir = "daily-reports"
os.makedirs(report_dir, exist_ok=True)

stocks = []
all_news = []

for ticker in tickers:
    try:
        t = yf.Ticker(ticker)
        info = t.info
        fast = t.fast_info

        price = fast.last_price
        prev = fast.previous_close
        change = price - prev
        pct = (change / prev) * 100

        low52 = info.get("fiftyTwoWeekLow")
        high52 = info.get("fiftyTwoWeekHigh")
        if low52 and high52 and high52 > low52:
            range_pct = (price - low52) / (high52 - low52) * 100
        else:
            range_pct = None

        target = info.get("targetMeanPrice")
        upside = ((target - price) / price * 100) if target else None

        # Collect news
        try:
            news = t.news or []
            for item in news[:2]:
                meta = item.get("content", {})
                title = meta.get("title", "")
                url = meta.get("canonicalUrl", {}).get("url", "") or meta.get("clickThroughUrl", {}).get("url", "")
                publisher = meta.get("provider", {}).get("displayName", "")
                if title and url:
                    all_news.append({"ticker": ticker, "title": title, "url": url, "publisher": publisher})
        except Exception:
            pass

        stocks.append({
            "ticker": ticker,
            "price": price,
            "change": change,
            "pct": pct,
            "low52": low52,
            "high52": high52,
            "range_pct": range_pct,
            "target": target,
            "upside": upside,
        })
    except Exception as e:
        print(f"Warning: failed to fetch {ticker}: {e}")
        stocks.append({
            "ticker": ticker, "price": None, "change": None, "pct": None,
            "low52": None, "high52": None, "range_pct": None,
            "target": None, "upside": None,
        })

# Markdown report
md_lines = [f"# Stock Report — {today}\n"]
for s in stocks:
    if s["price"] is None:
        md_lines.append(f"- **{s['ticker']}**: unavailable")
    else:
        arrow = "▲" if s["change"] >= 0 else "▼"
        line = f"- **{s['ticker']}**: ${s['price']:.2f} {arrow} {s['pct']:+.2f}%"
        if s["target"]:
            line += f" | Target: ${s['target']:.2f} ({s['upside']:+.1f}%)"
        md_lines.append(line)

md_path = os.path.join(report_dir, f"{today}.md")
with open(md_path, "w") as f:
    f.write("\n".join(md_lines) + "\n")

# HTML cards
def card_html(s):
    if s["price"] is None:
        return f'''<div class="card"><div class="card-header"><span class="ticker">{s["ticker"]}</span><span class="neutral">unavailable</span></div></div>'''

    up = s["change"] >= 0
    arrow = "▲" if up else "▼"
    change_cls = "up" if up else "down"

    range_html = ""
    if s["range_pct"] is not None:
        rp = min(max(s["range_pct"], 0), 100)
        range_html = f'''
      <div class="range-wrap">
        <span class="range-label">${s["low52"]:.2f}</span>
        <div class="range-bar"><div class="range-fill" style="width:{rp:.1f}%"></div></div>
        <span class="range-label">${s["high52"]:.2f}</span>
        <span class="range-pct">{rp:.0f}%</span>
      </div>'''

    target_html = ""
    if s["target"]:
        t_cls = "up" if s["upside"] >= 0 else "down"
        target_html = f'<div class="target {t_cls}">🎯 Analyst target: ${s["target"]:.2f} <span>({s["upside"]:+.2f}% upside)</span></div>'

    return f'''<div class="card">
      <div class="card-header">
        <span class="ticker">{s["ticker"]}</span>
        <span class="price">${s["price"]:.2f}</span>
        <span class="change {change_cls}">{arrow} {s["pct"]:+.2f}%</span>
      </div>{range_html}
      {target_html}
    </div>'''

cards = "\n".join(card_html(s) for s in stocks)

news_items = ""
seen = set()
for n in all_news:
    if n["url"] not in seen:
        seen.add(n["url"])
        news_items += f'<li><span class="news-ticker">[{n["ticker"]}]</span> <a href="{n["url"]}" target="_blank">{n["title"]}</a><span class="publisher"> — {n["publisher"]}</span></li>'

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Daily Stock Summary</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         background: #0f1117; color: #e2e8f0; padding: 16px; }}
  h1 {{ font-size: 1.3rem; font-weight: 700; color: #f8fafc; }}
  .date {{ font-size: 0.85rem; color: #94a3b8; margin-bottom: 20px; }}
  .section-title {{ font-size: 0.75rem; font-weight: 600; letter-spacing: .08em;
                    text-transform: uppercase; color: #64748b; margin: 20px 0 10px; }}
  .card {{ background: #1e2330; border-radius: 12px; padding: 14px 16px; margin-bottom: 10px; }}
  .card-header {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}
  .ticker {{ font-size: 1.1rem; font-weight: 700; color: #f8fafc; min-width: 60px; }}
  .price {{ font-size: 1.1rem; font-weight: 600; color: #cbd5e1; flex: 1; }}
  .change {{ font-size: 1rem; font-weight: 600; padding: 2px 8px; border-radius: 6px; }}
  .up {{ color: #4ade80; background: #14532d33; }}
  .down {{ color: #f87171; background: #7f1d1d33; }}
  .neutral {{ color: #94a3b8; }}
  .range-wrap {{ display: flex; align-items: center; gap: 6px; margin-top: 10px;
                 font-size: 0.75rem; color: #64748b; flex-wrap: wrap; }}
  .range-bar {{ flex: 1; min-width: 80px; height: 6px; background: #334155;
                border-radius: 3px; overflow: hidden; }}
  .range-fill {{ height: 100%; background: linear-gradient(90deg, #3b82f6, #8b5cf6);
                 border-radius: 3px; }}
  .range-pct {{ color: #94a3b8; font-size: 0.72rem; }}
  .target {{ margin-top: 8px; font-size: 0.8rem; color: #94a3b8; }}
  .target.up span {{ color: #4ade80; }}
  .target.down span {{ color: #f87171; }}
  .news-list {{ list-style: none; }}
  .news-list li {{ padding: 10px 0; border-bottom: 1px solid #1e2330; font-size: 0.85rem; line-height: 1.5; }}
  .news-list li:last-child {{ border-bottom: none; }}
  .news-ticker {{ color: #60a5fa; font-weight: 600; margin-right: 4px; }}
  a {{ color: #e2e8f0; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .publisher {{ color: #64748b; }}
  .disclaimer {{ margin-top: 20px; font-size: 0.73rem; color: #475569;
                 border-top: 1px solid #1e2330; padding-top: 12px; }}
</style>
</head>
<body>
  <h1>📊 Daily Stock Summary</h1>
  <div class="date">{date_str}</div>

  <div class="section-title">💼 Watchlist</div>
  {cards}

  <div class="section-title">📰 Top Headlines</div>
  <ul class="news-list">
    {news_items}
  </ul>

  <p class="disclaimer">⚠️ Analyst targets are Wall Street consensus estimates via Yahoo Finance. Not investment advice.</p>
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
    lines = [f"📊 *Stock Summary — {today}*\n"]
    for s in stocks:
        if s["price"] is None:
            lines.append(f"• *{s['ticker']}*: unavailable")
        else:
            arrow = "🟢" if s["change"] >= 0 else "🔴"
            line = f"{arrow} *{s['ticker']}*: ${s['price']:.2f} ({s['pct']:+.2f}%)"
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
