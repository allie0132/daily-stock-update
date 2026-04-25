import json
import os
from datetime import date
import yfinance as yf

with open("config.json") as f:
    config = json.load(f)

tickers = config["tickers"]
today = date.today().isoformat()
report_dir = "daily-reports"
os.makedirs(report_dir, exist_ok=True)

lines = [f"# Stock Report — {today}\n"]
for ticker in tickers:
    info = yf.Ticker(ticker).fast_info
    price = info.last_price
    prev = info.previous_close
    change = price - prev
    pct = (change / prev) * 100
    arrow = "▲" if change >= 0 else "▼"
    lines.append(f"- **{ticker}**: ${price:.2f}  {arrow} {pct:+.2f}%")

report_path = os.path.join(report_dir, f"{today}.md")
with open(report_path, "w") as f:
    f.write("\n".join(lines) + "\n")

print(f"Report saved to {report_path}")
