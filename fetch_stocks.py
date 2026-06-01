import json
import os
import urllib.request
from datetime import date, datetime
from zoneinfo import ZoneInfo
import yfinance as yf

with open("config.json") as f:
    config = json.load(f)

SECTORS = config["sectors"]
tickers = list(dict.fromkeys(t for ts in SECTORS.values() for t in ts))
universe = list(dict.fromkeys(config.get("universe", [])))
today = date.today().isoformat()
now_et = datetime.now(ZoneInfo("America/New_York"))
date_str = now_et.strftime("%A, %b %d %Y · %I:%M %p ET")

report_type = os.environ.get("REPORT_TYPE", "open")
report_label = "🔔 Market Open" if report_type == "open" else "🔔 Market Close"
report_dir = "daily-reports"
os.makedirs(report_dir, exist_ok=True)

for f in os.listdir(report_dir):
    if f.endswith(".html") or f.endswith(".md"):
        os.remove(os.path.join(report_dir, f))

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
        rsi = None
        ma50 = None
        try:
            hist6 = t.history(period="6mo")
            if len(hist6) >= 2:
                for period, n in [("6mo", None), ("3mo", 63), ("1mo", 21)]:
                    h = hist6.iloc[-n:] if n else hist6
                    chart_data[period]["dates"] = [d.strftime("%b %d") for d in h.index]
                    chart_data[period]["prices"] = [round(float(p), 2) for p in h["Close"]]
                week_start = hist6["Close"].iloc[-6] if len(hist6) >= 6 else hist6["Close"].iloc[0]
                week_pct = (price - week_start) / week_start * 100
            if len(hist6) >= 15:
                delta = hist6["Close"].diff().dropna()
                gain = delta.clip(lower=0).rolling(14).mean()
                loss = (-delta.clip(upper=0)).rolling(14).mean()
                rs = gain / loss
                rsi = float((100 - 100 / (1 + rs)).iloc[-1])
            if len(hist6) >= 50:
                ma50 = float(hist6["Close"].rolling(50).mean().iloc[-1])
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

        trade_amount = price * today_vol if today_vol else None
        stocks.append({
            "ticker": ticker, "price": price, "change": change, "pct": pct,
            "low52": low52, "high52": high52, "range_pct": range_pct,
            "target": target, "upside": upside,
            "week_pct": week_pct, "high_volume": high_volume,
            "today_vol": today_vol, "trade_amount": trade_amount,
            "rsi": rsi, "ma50": ma50,
            "chart_data": chart_data,
        })
    except Exception as e:
        print(f"Warning: failed to fetch {ticker}: {e}")
        stocks.append({
            "ticker": ticker, "price": None, "change": None, "pct": None,
            "low52": None, "high52": None, "range_pct": None,
            "target": None, "upside": None, "week_pct": None, "high_volume": False,
            "today_vol": None, "trade_amount": None,
            "chart_data": {"1mo": {"dates": [], "prices": []}, "3mo": {"dates": [], "prices": []}, "6mo": {"dates": [], "prices": []}},
        })

# ── Universe bulk fetch (for ranked lists) ───────────────────
extra_tickers = [t for t in universe if t not in set(tickers)]
universe_stocks = []
if extra_tickers:
    try:
        bulk = yf.download(extra_tickers, period="2d", auto_adjust=True,
                           progress=False, threads=True)
        close = bulk["Close"] if len(extra_tickers) > 1 else bulk["Close"].to_frame(extra_tickers[0])
        volume = bulk["Volume"] if len(extra_tickers) > 1 else bulk["Volume"].to_frame(extra_tickers[0])
        for t in extra_tickers:
            try:
                prices = close[t].dropna()
                vols = volume[t].dropna()
                if len(prices) < 2:
                    continue
                price = float(prices.iloc[-1])
                prev  = float(prices.iloc[-2])
                pct   = (price - prev) / prev * 100
                vol   = int(vols.iloc[-1]) if len(vols) else 0
                universe_stocks.append({
                    "ticker": t, "price": price, "pct": pct,
                    "trade_amount": price * vol if vol else None,
                    "upside": None, "target": None,
                })
            except Exception:
                pass
    except Exception as e:
        print(f"Warning: universe bulk fetch failed: {e}")

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

    sig = s.get("signal")
    sig_badge = f'<span class="sig sig-{sig["tag"]}">{sig["label"]}</span>' if sig else ""
    reasons_html = (f'<div class="sig-reasons">{" · ".join(sig["reasons"])}</div>' if sig and sig["reasons"] else "")

    return f'''<div class="card">
      <div class="card-header">
        <span class="ticker">{s["ticker"]}</span>
        <span class="change {change_cls}">{arrow} {s["pct"]:+.2f}%</span>
        {sig_badge}{vol_badge}
      </div>
      {reasons_html}
      {metrics_html}
      {chart_html}
      {range_html}
    </div>'''

# ── Signal scoring ───────────────────────────────────────────
def compute_signal(s):
    score = 0
    reasons = []
    explanation_parts = []

    if s.get("upside") is not None and s.get("target"):
        if s["upside"] > 30:
            score += 3; reasons.append(f"analyst upside {s['upside']:+.0f}%")
            explanation_parts.append(f"Analyst consensus target ${s['target']:.2f} implies {s['upside']:+.0f}% upside — strong undervaluation signal.")
        elif s["upside"] > 15:
            score += 2; reasons.append(f"analyst upside {s['upside']:+.0f}%")
            explanation_parts.append(f"Analyst target ${s['target']:.2f} implies {s['upside']:+.0f}% upside.")
        elif s["upside"] > 5:
            score += 1; reasons.append(f"analyst upside {s['upside']:+.0f}%")
            explanation_parts.append(f"Analyst target ${s['target']:.2f} implies modest {s['upside']:+.0f}% upside.")
        elif s["upside"] < -10:
            score -= 2; reasons.append(f"above target {s['upside']:+.0f}%")
            explanation_parts.append(f"Stock is trading {abs(s['upside']):.0f}% above analyst target of ${s['target']:.2f} — overvalued by consensus.")
        elif s["upside"] < 0:
            score -= 1; reasons.append(f"above target {s['upside']:+.0f}%")
            explanation_parts.append(f"Stock has exceeded analyst target of ${s['target']:.2f} by {abs(s['upside']):.0f}%.")

    if s.get("range_pct") is not None:
        if s["range_pct"] < 20:
            score += 2; reasons.append("near 52W low")
            explanation_parts.append(f"Trading near its 52-week low ({s['range_pct']:.0f}% of range) — historically cheap entry point.")
        elif s["range_pct"] < 35:
            score += 1; reasons.append("low in 52W range")
            explanation_parts.append(f"In the lower portion of its 52-week range ({s['range_pct']:.0f}%) — reasonable valuation vs recent history.")
        elif s["range_pct"] > 85:
            score -= 2; reasons.append("near 52W high")
            explanation_parts.append(f"Trading near its 52-week high ({s['range_pct']:.0f}% of range) — limited upside from current levels.")
        elif s["range_pct"] > 70:
            score -= 1; reasons.append("high in 52W range")
            explanation_parts.append(f"In the upper portion of its 52-week range ({s['range_pct']:.0f}%) — elevated vs recent history.")

    if s.get("rsi") is not None:
        if s["rsi"] < 30:
            score += 2; reasons.append(f"RSI oversold {s['rsi']:.0f}")
            explanation_parts.append(f"RSI at {s['rsi']:.0f} — heavily oversold, market may have overreacted, bounce likely.")
        elif s["rsi"] < 40:
            score += 1; reasons.append(f"RSI low {s['rsi']:.0f}")
            explanation_parts.append(f"RSI at {s['rsi']:.0f} — approaching oversold territory, potential reversal ahead.")
        elif s["rsi"] > 70:
            score -= 2; reasons.append(f"RSI overbought {s['rsi']:.0f}")
            explanation_parts.append(f"RSI at {s['rsi']:.0f} — overbought, high risk of near-term pullback.")
        elif s["rsi"] > 60:
            score -= 1; reasons.append(f"RSI high {s['rsi']:.0f}")
            explanation_parts.append(f"RSI at {s['rsi']:.0f} — elevated momentum, may be getting stretched.")

    if s.get("ma50") and s.get("price"):
        gap = (s["price"] - s["ma50"]) / s["ma50"] * 100
        if gap > 5:
            score -= 1; reasons.append("far above MA50")
            explanation_parts.append(f"Price is {gap:.0f}% above its 50-day moving average — extended, mean reversion risk.")
        elif gap > 0:
            score += 0.5
        elif gap < -5:
            score += 1; reasons.append("below MA50")
            explanation_parts.append(f"Price is {abs(gap):.0f}% below its 50-day moving average — potential recovery play.")
        else:
            score -= 0.5

    if s.get("week_pct") is not None:
        if s["week_pct"] > 5:
            score -= 1; reasons.append(f"up {s['week_pct']:+.1f}% this week")
            explanation_parts.append(f"Up {s['week_pct']:+.1f}% this week — short-term momentum may be overdone.")
        elif s["week_pct"] < -5:
            score += 1; reasons.append(f"down {s['week_pct']:+.1f}% this week")
            explanation_parts.append(f"Down {s['week_pct']:+.1f}% this week — recent weakness may be a buying opportunity.")

    if score >= 4:    label, tag = "Strong Buy",  "strong-buy"
    elif score >= 2:  label, tag = "Buy",          "buy"
    elif score >= -1: label, tag = "Hold",         "hold"
    elif score >= -3: label, tag = "Sell",         "sell"
    else:             label, tag = "Strong Sell",  "strong-sell"

    return {"score": score, "label": label, "tag": tag,
            "reasons": reasons[:3], "explanation": " ".join(explanation_parts)}

for s in stocks:
    if s["price"] is not None:
        s["signal"] = compute_signal(s)
    else:
        s["signal"] = None

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

# ── Signals overview ─────────────────────────────────────────
sig_order = {"Strong Buy": 0, "Buy": 1, "Hold": 2, "Sell": 3, "Strong Sell": 4}
sig_groups = {}
for s in valid:
    lbl = s["signal"]["label"]
    sig_groups.setdefault(lbl, []).append(s)

signals_html = '<div class="section-title">🔎 Buy / Sell Signals</div>'
for lbl in ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"]:
    items = sig_groups.get(lbl, [])
    if not items: continue
    tag = items[0]["signal"]["tag"]
    signals_html += f'<div class="card" style="margin-bottom:10px"><div style="margin-bottom:10px"><span class="sig sig-{tag}">{lbl}</span></div>'
    for s in sorted(items, key=lambda x: x["signal"]["score"], reverse=True):
        explanation = s["signal"].get("explanation") or "No analysis available."
        signals_html += f'<div class="sig-card" style="margin-bottom:8px"><div class="sig-card-ticker">{s["ticker"]}</div><div class="sig-card-reason">{explanation}</div></div>'
    signals_html += '</div>'

# ── Dynamic ranked lists ─────────────────────────────────────
def fmt_amount(v):
    if v is None: return "—"
    if v >= 1e9: return f"${v/1e9:.2f}B"
    if v >= 1e6: return f"${v/1e6:.1f}M"
    return f"${v:,.0f}"

N = 5

all_rankable = valid + universe_stocks
top_trade    = sorted([s for s in all_rankable if s["trade_amount"]], key=lambda s: s["trade_amount"], reverse=True)[:N]
top_gaining  = sorted(all_rankable, key=lambda s: s["pct"], reverse=True)[:N]
top_losing   = sorted(all_rankable, key=lambda s: s["pct"])[:N]
top_upside   = sorted([s for s in valid if s["upside"] is not None], key=lambda s: s["upside"], reverse=True)[:N]

def ranked_rows(items, cols_fn):
    return "".join(
        f'<tr>{"".join(f"<td>{c}</td>" for c in cols_fn(s))}</tr>'
        for s in items
    )

def pct_cell(val):
    cls = "up plain" if val >= 0 else "down plain"
    arrow = "▲" if val >= 0 else "▼"
    return f'<span class="{cls}">{arrow}{val:+.2f}%</span>'

def ranked_html(title, items, cols_fn):
    rows = ranked_rows(items, cols_fn)
    return f'<div class="section-title">{title}</div><div class="card"><table class="tt-table">{rows}</table></div>'

dynamic_lists_html = (
    ranked_html("💰 Top Trade Amount", top_trade,
        lambda s: [f'<span class="tt-ticker">{s["ticker"]}</span>',
                   f'<span class="tt-amt">{fmt_amount(s["trade_amount"])}</span>',
                   pct_cell(s["pct"])]) +
    ranked_html("📈 Top Increasing", top_gaining,
        lambda s: [f'<span class="tt-ticker">{s["ticker"]}</span>',
                   f'<span class="tt-price">${s["price"]:.2f}</span>',
                   pct_cell(s["pct"])]) +
    ranked_html("📉 Top Decreasing", top_losing,
        lambda s: [f'<span class="tt-ticker">{s["ticker"]}</span>',
                   f'<span class="tt-price">${s["price"]:.2f}</span>',
                   pct_cell(s["pct"])]) +
    (ranked_html("🎯 Top Analyst Upside", top_upside,
        lambda s: [f'<span class="tt-ticker">{s["ticker"]}</span>',
                   f'<span class="tt-price">${s["price"]:.2f}</span>',
                   f'<span class="up plain">→ ${s["target"]:.2f} ({s["upside"]:+.1f}%)</span>'])
     if top_upside else "")
)

# ── Sector groups ─────────────────────────────────────────────
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
  .tt-table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
  .tt-table tr {{ border-bottom: 1px solid #0f1117; }}
  .tt-table tr:last-child {{ border-bottom: none; }}
  .tt-table td {{ padding: 7px 4px; }}
  .sig {{ font-size: 0.7rem; font-weight: 700; padding: 2px 7px; border-radius: 4px; }}
  .sig-strong-buy  {{ background: #14532d; color: #4ade80; }}
  .sig-buy         {{ background: #1e3a1e; color: #86efac; }}
  .sig-hold        {{ background: #2d2a14; color: #fde68a; }}
  .sig-sell        {{ background: #3a1e1e; color: #fca5a5; }}
  .sig-strong-sell {{ background: #7f1d1d; color: #f87171; }}
  .sig-reasons {{ font-size: 0.7rem; color: #64748b; margin-bottom: 8px; }}
  .signals-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
  .sig-card {{ background: #0f1117; border-radius: 8px; padding: 8px 10px; }}
  .sig-card-ticker {{ font-weight: 700; color: #f8fafc; font-size: 0.9rem; }}
  .sig-card-reason {{ font-size: 0.68rem; color: #64748b; margin-top: 3px; }}
  .tt-ticker {{ font-weight: 700; color: #f8fafc; width: 60px; }}
  .tt-amt {{ font-weight: 600; color: #94a3b8; width: 100px; }}
  .tt-price {{ color: #94a3b8; width: 80px; }}
  .disclaimer {{ margin-top: 20px; font-size: 0.73rem; color: #475569;
                 border-top: 1px solid #1e2330; padding-top: 12px; }}
</style>
</head>
<body>
  <h1>📊 {report_label}</h1>
  <div class="date">{date_str}</div>
  {summary_html}
  {signals_html}
  {dynamic_lists_html}
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
    lines = [f"📊 *{report_label} — {today}*", f"▲ {up_count} up  ▼ {down_count} down  |  Best: {best['ticker']} {best['pct']:+.2f}%  Worst: {worst['ticker']} {worst['pct']:+.2f}%"]
    for label, items, row_fn in [
        ("📈 Top Gaining",       top_gaining,  lambda s: f"{s['ticker']:<5} ${s['price']:>8.2f}  ▲{s['pct']:+.2f}%"),
        ("📉 Top Losing",        top_losing,   lambda s: f"{s['ticker']:<5} ${s['price']:>8.2f}  ▼{s['pct']:+.2f}%"),
        ("💰 Top Trade Amount",  top_trade,    lambda s: f"{s['ticker']:<5} {fmt_amount(s['trade_amount']):<10}  {'▲' if s['pct']>=0 else '▼'}{s['pct']:+.2f}%"),
        ("🎯 Top Analyst Upside", top_upside,  lambda s: f"{s['ticker']:<5} → ${s['target']:.2f} ({s['upside']:+.1f}%)"),
    ]:
        if not items: continue
        lines.append(f"\n`{label}`")
        for s in items:
            lines.append(f"`{row_fn(s)}`")
    lines.append(f"\n[Full report](https://allie0132.github.io/daily-stock-update/daily-reports/{today}.html)")
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
