"""Compare our scores with EdgeFinder readings taken Oct 23 2026 about 11:30 AM PT."""
import pandas as pd, os, sys, subprocess
H = os.path.dirname(os.path.abspath(__file__))
# Rebuild the scores the way they stood at 11:30 AM PT on Oct 23 2026 (before the 12:30 PM PT COT release),
# from the cached data, then compare.
if "--no-run" not in sys.argv:
    env = dict(os.environ, EDGE_COT_BEFORE="2026-10-20")
    subprocess.run([sys.executable, os.path.join(H, "edge_job.py"), "--offline"], env=env, check=True, capture_output=True)
ref = pd.read_csv(os.path.join(H, "tests", "edgefinder_reference.csv"))
top = pd.read_csv(os.path.join(H, "output", "top_setups.csv")).set_index("symbol")
parts = ["technicals", "cot", "crowd", "growth", "inflation", "jobs"]
rows = []
for r in ref.itertuples():
    o = top.loc[r.ours]
    d = dict(symbol=r.symbol, theirs=r.score, ours=o.score, bias_theirs=r.bias, bias_ours=o.bias)
    for p in parts:
        t = getattr(r, p); d[p] = "%s/%+d" % ("" if pd.isna(t) else "%+d" % t, o[p]); d[p + "_ok"] = pd.isna(t) or int(t) == o[p]
    rows.append(d)
c = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print(c[["symbol", "theirs", "ours", "bias_theirs", "bias_ours"] + parts].to_string(index=False))
print("\nexact total: %d/%d, same bias: %d/%d, within 1: %d/%d" % ((c.theirs == c.ours).sum(), len(c), (c.bias_theirs == c.bias_ours).sum(), len(c), ((c.theirs - c.ours).abs() <= 1).sum(), len(c)))
for p in parts: print("%-10s parts matching %d/%d" % (p, c[p + "_ok"].sum(), len(c)))
c.to_csv(os.path.join(H, "output", "calibration_vs_edgefinder.csv"), index=False)
