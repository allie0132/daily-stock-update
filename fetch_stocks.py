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

for f in os.listdir(report_dir):
    if f.endswith(".html") or f.endswith(".md"):
        os.remove(os.path.join(report_dir, f))

SECTORS = {
    "💡 Semiconductors": ["NVDA", "MU", "INTC", "AMD"],
    "🌐 Big Tech":        ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA"],
}

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
        range_pct = ((price - low52) / (high52 - low52) * 100) if low52 and high52 and high52 > low52 else None

        target = info.get("targetMeanPrice")
        upside = ((target - price) / price * 100) if target else None

        # 1-month history + 1-week change
        week_pct = None
        chart_data = {"1mo": {"dates": [], "prices": []}, "3mo": {"dates": [], "prices": []}, "6mo": {"dates": [], "prices": []}}
        try:
            hist6 = t.history(period="6mo")
            if len(hist6) >= 2:
                for period, n in [("6mo", None), ("3mo", 63), ("1mo", 21)]:
                    h = hist6.iloc[-n:] if n else hist6
                    chart_data[period]["dates"] = [d.strftime("%b %d") for d in h.index]
                    chart_data[period]["prices"] = [round(float(p), 2) for p in h["Close"]]
                week_start = hist6["Close"].iloc[-6] if len(hist6) >= 6 else hist6["Close"].iloc[0]
                week_pct = (price - week_start) / week_start * 100
        except Exception:
            pass

        # Volume vs average
        volume = fast.three_month_average_volume or 0
        today_vol = info.get("regularMarketVolume") or 0
        high_volume = today_vol > volume * 1.5 if volume and today_vol else False

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
            "ticker": ticker, "price": price, "change": change, "pct": pct,
            "low52": low52, "high52": high52, "range_pct": range_pct,
            "target": target, "upside": upside,
            "week_pct": week_pct, "high_volume": high_volume,
            "chart_data": chart_data,
        })
    except Exception as e:
        print(f"Warning: failed to fetch {ticker}: {e}")
        stocks.append({
            "ticker": ticker, "price": None, "change": None, "pct": None,
            "low52": None, "high52": None, "range_pct": None,
            "target": None, "upside": None, "week_pct": None, "high_volume": False,
            "chart_data": {"1mo": {"dates": [], "prices": []}, "3mo": {"dates": [], "prices": []}, "6mo": {"dates": [], "prices": []}},
        })

# Markdown
md_lines = [f"# Stock Report — {today}\n"]
for s in stocks:
    if s["price"] is None:
        md_lines.append(f"- **{s['ticker']}**: unavailable")
    else:
        arrow = "▲" if s["change"] >= 0 else "▼"
        line = f"- **{s['ticker']}**: ${s['price']:.2f} {arrow} {s['pct']:+.2f}%"
        if s["week_pct"] is not None:
            line += f" | 1W: {s['week_pct']:+.2f}%"
        if s["target"]:
            line += f" | Target: ${s['target']:.2f} ({s['upside']:+.1f}%)"
        md_lines.append(line)

md_path = os.path.join(report_dir, f"{today}.md")
with open(md_path, "w") as f:
    f.write("\n".join(md_lines) + "\n")

# ── HTML helpers ────────────────────────────────────────────
def pct_span(val, label=""):
    if val is None: return f'<span class="neutral">{label}—</span>'
    cls = "up" if val >= 0 else "down"
    arrow = "▲" if val >= 0 else "▼"
    return f'<span class="{cls}">{label}{arrow} {val:+.2f}%</span>'

def metric(label, value_html, tooltip=""):
    title = f'title="{tooltip}"' if tooltip else ""
    return f'<div class="metric" {title}><span class="metric-label">{label}</span><span class="metric-value">{value_html}</span></div>'

def card_html(s):
    if s["price"] is None:
        return f'<div class="card"><div class="card-header"><span class="ticker">{s["ticker"]}</span><span class="neutral">unavailable</span></div></div>'

    up = s["change"] >= 0
    change_cls = "up" if up else "down"
    arrow = "▲" if up else "▼"
    vol_badge = '<span class="vol-badge">⚡ High Vol</span>' if s["high_volume"] else ""

    # Metrics row
    day_html = f'<span class="{change_cls} plain">{arrow} {s["pct"]:+.2f}%</span>'
    week_html = pct_span(s["week_pct"]) if s["week_pct"] is not None else '<span class="neutral">—</span>'
    target_html = f'<span class="up plain">${s["target"]:.2f} ({s["upside"]:+.1f}%)</span>' if s["target"] and s["upside"] >= 0 else (f'<span class="down plain">${s["target"]:.2f} ({s["upside"]:+.1f}%)</span>' if s["target"] else '<span class="neutral">—</span>')

    metrics_html = f'''
      <div class="metrics-grid">
        {metric("Price (USD)", f'<span class="price-val">${s["price"]:.2f}</span>')}
        {metric("Day Change", day_html, "Change vs previous close")}
        {metric("1-Week Change", week_html, "Change over the past 5 trading days")}
        {metric("Analyst Target", target_html, "Wall Street consensus mean price target")}
      </div>'''

    range_html = ""
    if s["range_pct"] is not None:
        rp = min(max(s["range_pct"], 0), 100)
        range_html = f'''
      <div class="range-section">
        <div class="range-label-row">
          <span class="range-label-text">52-Week Range <span class="range-hint">(where current price sits)</span></span>
          <span class="range-pct">{rp:.0f}%</span>
        </div>
        <div class="range-wrap">
          <span class="range-val">Low<br>${s["low52"]:.2f}</span>
          <div class="range-bar"><div class="range-fill" style="width:{rp:.1f}%"></div></div>
          <span class="range-val">High<br>${s["high52"]:.2f}</span>
        </div>
      </div>'''

    chart_html = ""
    if s["chart_data"]["1mo"]["prices"]:
        tid = s["ticker"].replace(".", "_")
        chart_html = f'''
      <div class="chart-section">
        <div class="chart-header">
          <span class="chart-label">Price History</span>
          <div class="chart-btns">
            <button class="cbtn active" onclick="setPeriod('{tid}','1mo',this)">1M</button>
            <button class="cbtn" onclick="setPeriod('{tid}','3mo',this)">3M</button>
            <button class="cbtn" onclick="setPeriod('{tid}','6mo',this)">6M</button>
          </div>
        </div>
        <canvas id="chart_{tid}" height="80"></canvas>
        <script>
          (function() {{
            window._sd = window._sd || {{}};
            window._sd["{tid}"] = {json.dumps(s["chart_data"])};
            var ctx = document.getElementById("chart_{tid}").getContext("2d");
            window._charts = window._charts || {{}};
            window._charts["{tid}"] = new Chart(ctx, {{
              type: "line",
              data: {{
                labels: {json.dumps(s["chart_data"]["1mo"]["dates"])},
                datasets: [{{
                  data: {json.dumps(s["chart_data"]["1mo"]["prices"])},
                  borderColor: "#475569",
                  borderWidth: 1.5,
                  pointRadius: 0,
                  tension: 0.3,
                  fill: true,
                  backgroundColor: "#47556920"
                }}]
              }},
              options: {{
                animation: false,
                plugins: {{ legend: {{ display: false }}, tooltip: {{
                  callbacks: {{ label: c => "$" + c.parsed.y.toFixed(2) }}
                }} }},
                scales: {{
                  x: {{ grid: {{ display: false }}, ticks: {{ maxTicksLimit: 5, color: "#475569", font: {{ size: 9 }} }} }},
                  y: {{ grid: {{ color: "#1a2236" }}, ticks: {{ color: "#475569", font: {{ size: 9 }},
                         callback: v => "$" + v }} }}
                }}
              }}
            }});
          }})();
        </script>
      </div>'''

    return f'''<div class="card">
      <div class="card-header">
        <span class="ticker">{s["ticker"]}</span>
        <span class="change {change_cls}">{arrow} {s["pct"]:+.2f}%</span>
        {vol_badge}
      </div>
      {metrics_html}
      {chart_html}
      {range_html}
    </div>'''

# ── Market summary ───────────────────────────────────────────
valid = [s for s in stocks if s["price"] is not None]
up_count = sum(1 for s in valid if s["pct"] >= 0)
down_count = len(valid) - up_count
best = max(valid, key=lambda s: s["pct"])
worst = min(valid, key=lambda s: s["pct"])
summary_html = f'''<div class="summary">
  <div class="summary-item"><span class="up">▲ {up_count} Up</span></div>
  <div class="summary-item"><span class="down">▼ {down_count} Down</span></div>
  <div class="summary-divider"></div>
  <div class="summary-item"><span class="summary-label">Best</span> <span class="up">{best["ticker"]} {best["pct"]:+.2f}%</span></div>
  <div class="summary-item"><span class="summary-label">Worst</span> <span class="down">{worst["ticker"]} {worst["pct"]:+.2f}%</span></div>
</div>'''

# ── Sector groups ────────────────────────────────────────────
stock_map = {s["ticker"]: s for s in stocks}
sector_html = ""
for sector_name, sector_tickers in SECTORS.items():
    sector_stocks = [stock_map[t] for t in sector_tickers if t in stock_map]
    cards = "\n".join(card_html(s) for s in sector_stocks)
    sector_html += f'<div class="section-title">{sector_name}</div>\n{cards}\n'

# Tickers not in any sector
sectored = {t for ts in SECTORS.values() for t in ts}
others = [s for s in stocks if s["ticker"] not in sectored]
if others:
    cards = "\n".join(card_html(s) for s in others)
    sector_html += f'<div class="section-title">📈 Other</div>\n{cards}\n'

# ── News ────────────────────────────────────────────────────
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
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         background: #0f1117; color: #e2e8f0; padding: 16px; max-width: 560px; margin: 0 auto; }}
  h1 {{ font-size: 1.3rem; font-weight: 700; color: #f8fafc; }}
  .date {{ font-size: 0.85rem; color: #94a3b8; margin-bottom: 12px; }}
  .summary {{ display: flex; gap: 12px; align-items: center; flex-wrap: wrap;
              background: #1e2330; border-radius: 10px; padding: 10px 14px;
              margin-bottom: 20px; font-size: 0.9rem; font-weight: 600; }}
  .summary-item {{ display: flex; align-items: center; gap: 4px; }}
  .summary-label {{ color: #64748b; font-weight: 400; font-size: 0.8rem; }}
  .summary-divider {{ width: 1px; height: 16px; background: #475569; }}
  .section-title {{ font-size: 0.75rem; font-weight: 600; letter-spacing: .08em;
                    text-transform: uppercase; color: #64748b; margin: 20px 0 10px; }}
  .card {{ background: #1e2330; border-radius: 12px; padding: 14px 16px; margin-bottom: 10px; }}
  .card-header {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 10px; }}
  .ticker {{ font-size: 1.15rem; font-weight: 700; color: #f8fafc; flex: 1; }}
  .change {{ font-size: 0.95rem; font-weight: 600; padding: 2px 10px; border-radius: 6px; }}
  .vol-badge {{ font-size: 0.7rem; font-weight: 600; background: #78350f44;
                color: #fbbf24; padding: 2px 6px; border-radius: 4px; }}
  .metrics-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 10px; }}
  .metric {{ background: #0f1117; border-radius: 8px; padding: 8px 10px;
             display: flex; flex-direction: column; gap: 3px; }}
  .metric-label {{ font-size: 0.68rem; color: #64748b; text-transform: uppercase;
                   letter-spacing: .06em; font-weight: 500; }}
  .metric-value {{ font-size: 0.9rem; font-weight: 600; }}
  .price-val {{ color: #f1f5f9; }}
  .up {{ color: #4ade80; background: #14532d33; }}
  .down {{ color: #f87171; background: #7f1d1d33; }}
  .up.plain, .down.plain {{ background: none; }}
  .change.up, .change.down {{ padding: 2px 10px; border-radius: 6px; }}
  .neutral {{ color: #64748b; }}
  .range-section {{ margin-top: 4px; }}
  .range-label-row {{ display: flex; justify-content: space-between; align-items: baseline;
                       font-size: 0.7rem; color: #64748b; margin-bottom: 6px; }}
  .range-label-text {{ text-transform: uppercase; letter-spacing: .05em; font-weight: 500; }}
  .range-hint {{ font-size: 0.65rem; color: #475569; text-transform: none; letter-spacing: 0; margin-left: 4px; }}
  .range-pct {{ color: #94a3b8; }}
  .range-wrap {{ display: flex; align-items: center; gap: 8px; }}
  .range-bar {{ flex: 1; height: 6px; background: #475569; border-radius: 3px; overflow: hidden; }}
  .range-fill {{ height: 100%; background: linear-gradient(90deg, #3b82f6, #8b5cf6); border-radius: 3px; }}
  .range-val {{ font-size: 0.68rem; color: #64748b; text-align: center; line-height: 1.3; }}
  .chart-section {{ margin-top: 12px; }}
  .chart-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }}
  .chart-label {{ font-size: 0.68rem; color: #475569; text-transform: uppercase; letter-spacing: .06em; }}
  .chart-btns {{ display: flex; gap: 4px; }}
  .cbtn {{ background: #0f1117; border: 1px solid #1e293b; color: #475569; font-size: 0.7rem;
            font-weight: 600; padding: 2px 7px; border-radius: 4px; cursor: pointer; }}
  .cbtn.active {{ background: #1e293b; color: #94a3b8; border-color: #475569; }}
  .cbtn:hover {{ color: #cbd5e1; }}
  .news-list {{ list-style: none; }}
  .news-list li {{ padding: 10px 0; border-bottom: 1px solid #1e2330;
                   font-size: 0.85rem; line-height: 1.5; }}
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
  {summary_html}
  {sector_html}
  <div class="section-title">📰 Top Headlines</div>
  <ul class="news-list">{news_items}</ul>
  <p class="disclaimer">⚠️ Analyst targets are Wall Street consensus estimates via Yahoo Finance. Not investment advice.</p>
  <script>
    function setPeriod(tid, period, btn) {{
      var c = window._charts[tid]; var d = window._sd[tid][period];
      c.data.labels = d.dates; c.data.datasets[0].data = d.prices; c.update();
      btn.closest('.chart-btns').querySelectorAll('.cbtn').forEach(function(b) {{ b.classList.remove('active'); }});
      btn.classList.add('active');
    }}
  </script>
</body>
</html>"""

html_path = os.path.join(report_dir, f"{today}.html")
with open(html_path, "w") as f:
    f.write(html)

index = f"""<!DOCTYPE html>
<html><head><meta http-equiv="refresh" content="0;url=daily-reports/{today}.html">
<title>Redirecting...</title></head>
<body>Redirecting to <a href="daily-reports/{today}.html">today's report</a>.</body></html>"""

with open("index.html", "w") as f:
    f.write(index)

print(f"Reports saved: {md_path}, {html_path}")

# Telegram
tg_token = os.environ.get("TELEGRAM_TOKEN")
tg_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
if tg_token and tg_chat_id:
    lines = [f"📊 *Stock Summary — {today}*", f"▲ {up_count} up · ▼ {down_count} down · Best: {best['ticker']} {best['pct']:+.2f}% · Worst: {worst['ticker']} {worst['pct']:+.2f}%\n"]
    for sector_name, sector_tickers in SECTORS.items():
        lines.append(f"*{sector_name}*")
        for t in sector_tickers:
            s = stock_map.get(t)
            if not s or s["price"] is None: continue
            arrow = "🟢" if s["pct"] >= 0 else "🔴"
            line = f"{arrow} *{s['ticker']}*: ${s['price']:.2f} ({s['pct']:+.2f}%)"
            if s["week_pct"] is not None:
                line += f" | 1W: {s['week_pct']:+.2f}%"
            lines.append(line)
        lines.append("")
    lines.append(f"[Full report](https://allie0132.github.io/daily-stock-update/daily-reports/{today}.html)")
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
