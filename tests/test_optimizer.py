import numpy as np
import pytest

from app.optimizer import Battery, optimize_dispatch, rule_based_dispatch


def ideal(**kw):
    """Lossless 1 MWh / 1 MW battery unless overridden."""
    base = dict(energy_capacity_mwh=1.0, power_rating_mw=1.0, charge_efficiency=1.0, discharge_efficiency=1.0)
    base.update(kw)
    return Battery(**base)


def test_buys_low_and_sells_high():
    s = optimize_dispatch([10.0, 50.0], ideal())
    np.testing.assert_allclose(s.charge_mw, [1, 0], atol=1e-6)
    np.testing.assert_allclose(s.discharge_mw, [0, 1], atol=1e-6)
    assert s.profit == pytest.approx(40.0)


def test_flat_prices_mean_no_trading():
    s = optimize_dispatch([30.0] * 24, Battery(energy_capacity_mwh=10, power_rating_mw=5))
    assert s.charge_mw.sum() == pytest.approx(0, abs=1e-6)
    assert s.profit == pytest.approx(0, abs=1e-6)


def test_losses_stop_unprofitable_trades():
    # 81% round-trip efficiency: a 10% price spread cannot pay for the losses
    b = ideal(charge_efficiency=0.9, discharge_efficiency=0.9)
    assert optimize_dispatch([100.0, 110.0], b).profit == pytest.approx(0, abs=1e-6)
    # a 30% spread can
    assert optimize_dispatch([100.0, 130.0], b).profit > 0


def test_degradation_cost_is_charged_per_mwh_discharged():
    s = optimize_dispatch([10.0, 50.0], ideal(degradation_cost_per_mwh=5.0))
    assert s.profit == pytest.approx(35.0)


def test_limits_and_energy_balance_hold_on_random_prices():
    rng = np.random.default_rng(0)
    b = Battery(energy_capacity_mwh=20, power_rating_mw=5, charge_efficiency=0.92, discharge_efficiency=0.94,
                initial_soc_mwh=4, final_soc_min_mwh=4)
    prices = rng.uniform(10, 80, 168)
    s = optimize_dispatch(prices, b)
    tol = 1e-6
    assert np.all(s.charge_mw <= b.power_rating_mw + tol) and np.all(s.discharge_mw <= b.power_rating_mw + tol)
    assert np.all(s.soc_mwh >= -tol) and np.all(s.soc_mwh <= b.energy_capacity_mwh + tol)
    assert s.soc_mwh[-1] >= b.final_soc_min_mwh - tol
    soc = b.initial_soc_mwh + np.cumsum(b.charge_efficiency * s.charge_mw - s.discharge_mw / b.discharge_efficiency)
    np.testing.assert_allclose(soc, s.soc_mwh, atol=1e-5)


def test_optimal_schedule_never_loses_to_rule_based_baseline():
    rng = np.random.default_rng(1)
    b = Battery(energy_capacity_mwh=20, power_rating_mw=5)
    for _ in range(20):
        prices = rng.uniform(15, 60, 24)
        assert optimize_dispatch(prices, b).profit >= rule_based_dispatch(prices, b).profit - 1e-6


def test_rule_based_respects_limits():
    b = Battery(energy_capacity_mwh=10, power_rating_mw=4)
    s = rule_based_dispatch([10, 10, 10, 10, 90, 90, 90, 90], b)
    assert np.all(s.soc_mwh <= 10 + 1e-9) and np.all(s.soc_mwh >= -1e-9)


def test_initial_soc_above_capacity_is_rejected():
    with pytest.raises(ValueError):
        optimize_dispatch([10, 20], ideal(initial_soc_mwh=2.0))
