"""REST API for battery dispatch optimization.

Run locally:  uvicorn app.main:app --reload
Interactive documentation is served at /docs.
"""
from fastapi import FastAPI, HTTPException

from . import __version__
from .optimizer import Battery, optimize_dispatch, rule_based_dispatch
from .schemas import CompareResponse, DispatchRequest, DispatchResponse, Period

app = FastAPI(
    title="Battery Dispatch Optimization API",
    version=__version__,
    description=("Computes the profit-maximizing charge and discharge schedule of a battery from electricity "
                 "prices by solving a linear program (HiGHS), and compares it with a rule-based baseline."),
)


def _battery(req: DispatchRequest) -> Battery:
    return Battery(**req.battery.model_dump())


def _response(method, req, sched) -> DispatchResponse:
    dt = req.interval_hours
    return DispatchResponse(
        method=method,
        profit=round(sched.profit, 2),
        energy_charged_mwh=round(float(sched.charge_mw.sum() * dt), 3),
        energy_discharged_mwh=round(float(sched.discharge_mw.sum() * dt), 3),
        schedule=[Period(period=t, price=req.prices[t], charge_mw=round(float(c), 3),
                         discharge_mw=round(float(d), 3), soc_mwh=round(float(s), 3))
                  for t, (c, d, s) in enumerate(zip(sched.charge_mw, sched.discharge_mw, sched.soc_mwh))],
    )


@app.get("/health")
def health():
    return {"status": "ok", "version": __version__}


@app.post("/dispatch/optimal", response_model=DispatchResponse)
def dispatch_optimal(req: DispatchRequest):
    try:
        sched = optimize_dispatch(req.prices, _battery(req), req.interval_hours)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _response("linear_program", req, sched)


@app.post("/dispatch/rule-based", response_model=DispatchResponse)
def dispatch_rule_based(req: DispatchRequest):
    sched = rule_based_dispatch(req.prices, _battery(req), req.interval_hours)
    return _response("rule_based", req, sched)


@app.post("/dispatch/compare", response_model=CompareResponse)
def dispatch_compare(req: DispatchRequest):
    opt = dispatch_optimal(req)
    rule = dispatch_rule_based(req)
    base = abs(rule.profit) if rule.profit != 0 else None
    gain = round(100 * (opt.profit - rule.profit) / base, 1) if base else 0.0
    return CompareResponse(optimal_profit=opt.profit, rule_based_profit=rule.profit,
                           improvement_pct=gain, optimal=opt, rule_based=rule)
