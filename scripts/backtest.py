"""Compare the optimal (LP) and rule-based schedules on every full day of PJM-based prices.

Usage:  python scripts/backtest.py [path/to/power_prices.csv]
The default data file is the price series from the battery arbitrage project.
"""
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from app.optimizer import Battery, optimize_dispatch, rule_based_dispatch  # noqa: E402

URL = "https://raw.githubusercontent.com/ekahorsu/battery-arbitrage-reinforcement-learning/main/power_prices.csv"
path = sys.argv[1] if len(sys.argv) > 1 else URL
df = pd.read_csv(path, parse_dates=["Datetime"])
days = [g["price"].to_numpy() for _, g in df.groupby(df["Datetime"].dt.date) if len(g) == 24]

battery = Battery(energy_capacity_mwh=20, power_rating_mw=5, charge_efficiency=0.95,
                  discharge_efficiency=0.95, degradation_cost_per_mwh=2.0)
lp = np.array([optimize_dispatch(p, battery).profit for p in days])
rule = np.array([rule_based_dispatch(p, battery).profit for p in days])

print(f"Days evaluated:                    {len(days)}")
print(f"Battery: 20 MWh / 5 MW, 95% charge and discharge efficiency, $2/MWh cycling cost")
print(f"Optimal (LP) mean daily profit:    ${lp.mean():,.2f}  (total ${lp.sum():,.0f})")
print(f"Rule-based mean daily profit:      ${rule.mean():,.2f}  (total ${rule.sum():,.0f})")
print(f"LP profit gain over rule-based:    {100 * (lp.sum() - rule.sum()) / rule.sum():.0f}%")
print(f"Days on which LP earned more:      {100 * np.mean(lp > rule + 1e-6):.0f}%")
