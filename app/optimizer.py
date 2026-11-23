"""Core algorithms: price-based battery scheduling.

`optimize_dispatch` solves a linear program for the profit-maximizing day-ahead
charge and discharge schedule of a battery that buys and sells energy at known
hourly prices (perfect foresight). `rule_based_dispatch` is a simple threshold
heuristic used as a baseline.
"""
from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog


@dataclass(frozen=True)
class Battery:
    energy_capacity_mwh: float          # usable energy, E
    power_rating_mw: float              # max charge/discharge power, P
    charge_efficiency: float = 0.95     # eta_c
    discharge_efficiency: float = 0.95  # eta_d
    initial_soc_mwh: float = 0.0        # state of charge at the start
    final_soc_min_mwh: float = 0.0      # minimum state of charge at the end
    degradation_cost_per_mwh: float = 0.0  # cost per MWh discharged


@dataclass
class Schedule:
    charge_mw: np.ndarray
    discharge_mw: np.ndarray
    soc_mwh: np.ndarray
    profit: float


def _profit(prices, charge, discharge, battery, dt):
    revenue = float(np.sum(prices * (discharge - charge)) * dt)
    return revenue - battery.degradation_cost_per_mwh * float(np.sum(discharge)) * dt


def optimize_dispatch(prices, battery: Battery, dt_hours: float = 1.0) -> Schedule:
    """Profit-maximizing schedule from a linear program solved with HiGHS.

    Decision variables (T periods each): charge c_t, discharge d_t, state of charge s_t.

        max   sum_t [ p_t (d_t - c_t) dt - k d_t dt ]
        s.t.  s_t = s_{t-1} + eta_c c_t dt - d_t dt / eta_d     (energy balance)
              0 <= c_t, d_t <= P,  0 <= s_t <= E,  s_T >= s_final_min
    """
    p = np.asarray(prices, dtype=float)
    T = len(p)
    b = battery
    dt = dt_hours
    if b.initial_soc_mwh > b.energy_capacity_mwh or b.final_soc_min_mwh > b.energy_capacity_mwh:
        raise ValueError("initial and final state of charge must not exceed the energy capacity")

    # variable vector x = [c_0..c_{T-1}, d_0..d_{T-1}, s_0..s_{T-1}]
    c_idx, d_idx, s_idx = np.arange(T), np.arange(T, 2 * T), np.arange(2 * T, 3 * T)
    cost = np.zeros(3 * T)
    cost[c_idx] = p * dt                                   # buying energy costs money
    cost[d_idx] = -(p - b.degradation_cost_per_mwh) * dt   # selling earns money (linprog minimizes)

    A_eq = np.zeros((T, 3 * T))
    b_eq = np.zeros(T)
    for t in range(T):
        A_eq[t, s_idx[t]] = 1.0
        if t > 0:
            A_eq[t, s_idx[t - 1]] = -1.0
        A_eq[t, c_idx[t]] = -b.charge_efficiency * dt
        A_eq[t, d_idx[t]] = dt / b.discharge_efficiency
        b_eq[t] = b.initial_soc_mwh if t == 0 else 0.0

    bounds = ([(0, b.power_rating_mw)] * T + [(0, b.power_rating_mw)] * T
              + [(0, b.energy_capacity_mwh)] * (T - 1) + [(b.final_soc_min_mwh, b.energy_capacity_mwh)])

    res = linprog(cost, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")
    if res.status != 0:
        raise RuntimeError(f"optimization failed: {res.message}")

    c = np.clip(res.x[c_idx], 0, None)
    d = np.clip(res.x[d_idx], 0, None)
    s = res.x[s_idx]
    return Schedule(c, d, s, _profit(p, c, d, b, dt))


def rule_based_dispatch(prices, battery: Battery, dt_hours: float = 1.0,
                        low_quantile: float = 0.2, high_quantile: float = 0.8) -> Schedule:
    """Baseline heuristic: charge at full power in the cheapest hours of the horizon (price at or below
    the `low_quantile` price) and discharge in the most expensive hours (at or above the `high_quantile`
    price), within power and energy limits and the required final state of charge."""
    p = np.asarray(prices, dtype=float)
    b = battery
    lo, hi = np.quantile(p, low_quantile), np.quantile(p, high_quantile)
    soc = b.initial_soc_mwh
    c, d, s = np.zeros(len(p)), np.zeros(len(p)), np.zeros(len(p))
    for t, price in enumerate(p):
        if price <= lo:
            room = (b.energy_capacity_mwh - soc) / (b.charge_efficiency * dt_hours)
            c[t] = max(0.0, min(b.power_rating_mw, room))
        elif price >= hi:
            avail = (soc - b.final_soc_min_mwh) * b.discharge_efficiency / dt_hours
            d[t] = max(0.0, min(b.power_rating_mw, avail))
        soc = soc + b.charge_efficiency * c[t] * dt_hours - d[t] * dt_hours / b.discharge_efficiency
        s[t] = soc
    return Schedule(c, d, s, _profit(p, c, d, b, dt_hours))
