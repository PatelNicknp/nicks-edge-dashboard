"""Write the static page shells. Data and layout live in site/js."""
import os

PAGES = [
    ("index.html", "top", "Top setups"),
    ("scorecard.html", "scorecard", "Scorecard"),
    ("gold.html", "gold", "Gold scorecard"),
    ("cot.html", "cot", "COT report"),
    ("cot-history.html", "cothist", "COT history"),
    ("sentiment.html", "sentiment", "Retail sentiment"),
    ("strength.html", "strength", "Economic strength"),
    ("econ-heat.html", "econheat", "Economic heatmap"),
    ("econ-tables.html", "econtables", "Economic tables"),
    ("carry.html", "carry", "Real yields and carry"),
    ("seasonality.html", "season", "Seasonality"),
    ("momentum.html", "momentum", "Momentum"),
    ("volatility.html", "volatility", "Volatility"),
    ("markets.html", "markets", "Market heatmap"),
    ("spreads.html", "spreads", "Spreads"),
    ("calendar.html", "calendar", "Economic calendar"),
    ("news.html", "news", "News feed"),
    ("backtest.html", "backtest", "Score backtest"),
    ("help.html", "help", "Updates and help"),
]

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Nick's Edge Dashboard</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 22 22'%3E%3Crect rx='6' width='22' height='22' fill='%232F81F7'/%3E%3C/svg%3E">
<link rel="stylesheet" href="css/desk.css">
</head>
<body data-page="{pid}">
<div id="app"></div>
<noscript><p class="noscript">This page needs JavaScript to read the data files.</p></noscript>
<script src="vendor/papaparse.min.js"></script>
<script src="vendor/chart.umd.min.js"></script>
<script src="js/desk.js"></script>
<script src="js/pages.js"></script>
</body>
</html>
"""


def main():
    root = os.path.dirname(os.path.abspath(__file__))
    for filename, pid, title in PAGES:
        path = os.path.join(root, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(TEMPLATE.format(title=title, pid=pid))
    print(len(PAGES), "pages")


if __name__ == "__main__":
    main()
