import json
import os

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
SAMPLE = json.load(open(os.path.join(os.path.dirname(__file__), "..", "examples", "sample_request.json")))


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_optimal_dispatch_on_sample_day():
    r = client.post("/dispatch/optimal", json=SAMPLE)
    assert r.status_code == 200
    body = r.json()
    assert body["method"] == "linear_program"
    assert len(body["schedule"]) == len(SAMPLE["prices"])
    assert body["profit"] > 0


def test_compare_endpoint():
    r = client.post("/dispatch/compare", json=SAMPLE)
    assert r.status_code == 200
    body = r.json()
    assert body["optimal_profit"] >= body["rule_based_profit"]


def test_invalid_battery_is_rejected():
    bad = {**SAMPLE, "battery": {**SAMPLE["battery"], "power_rating_mw": -1}}
    assert client.post("/dispatch/optimal", json=bad).status_code == 422


def test_initial_soc_above_capacity_is_rejected():
    bad = {**SAMPLE, "battery": {**SAMPLE["battery"], "initial_soc_mwh": 999}}
    assert client.post("/dispatch/optimal", json=bad).status_code == 422


def test_too_few_prices_is_rejected():
    assert client.post("/dispatch/optimal", json={**SAMPLE, "prices": [30.0]}).status_code == 422
