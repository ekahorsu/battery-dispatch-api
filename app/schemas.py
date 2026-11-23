from typing import List

from pydantic import BaseModel, Field, model_validator


class BatterySpec(BaseModel):
    energy_capacity_mwh: float = Field(..., gt=0, le=10_000, description="Usable energy capacity (MWh)")
    power_rating_mw: float = Field(..., gt=0, le=10_000, description="Maximum charge and discharge power (MW)")
    charge_efficiency: float = Field(0.95, gt=0, le=1)
    discharge_efficiency: float = Field(0.95, gt=0, le=1)
    initial_soc_mwh: float = Field(0.0, ge=0, description="State of charge at the start (MWh)")
    final_soc_min_mwh: float = Field(0.0, ge=0, description="Minimum state of charge at the end (MWh)")
    degradation_cost_per_mwh: float = Field(0.0, ge=0, description="Cycling cost per MWh discharged ($/MWh)")

    @model_validator(mode="after")
    def soc_within_capacity(self):
        if self.initial_soc_mwh > self.energy_capacity_mwh or self.final_soc_min_mwh > self.energy_capacity_mwh:
            raise ValueError("initial_soc_mwh and final_soc_min_mwh must not exceed energy_capacity_mwh")
        return self


class DispatchRequest(BaseModel):
    prices: List[float] = Field(..., min_length=2, max_length=744,
                                description="Electricity prices for each period ($/MWh), e.g. 24 hourly day-ahead prices")
    interval_hours: float = Field(1.0, gt=0, le=24, description="Length of each period (hours)")
    battery: BatterySpec

    model_config = {
        "json_schema_extra": {
            "example": {
                "prices": [24.3, 21.41, 20.45, 19.29, 21.57, 20.75, 26.78, 28.72, 26.41, 25.56, 29.74, 32.56, 22.77, 25.86, 25.57, 35.48, 29.19, 29.33, 28.12, 27.13, 25.94, 30.65, 31.3, 24.16],
                "interval_hours": 1.0,
                "battery": {"energy_capacity_mwh": 20, "power_rating_mw": 5, "charge_efficiency": 0.95,
                            "discharge_efficiency": 0.95, "initial_soc_mwh": 0, "final_soc_min_mwh": 0,
                            "degradation_cost_per_mwh": 2.0},
            }
        }
    }


class Period(BaseModel):
    period: int
    price: float
    charge_mw: float
    discharge_mw: float
    soc_mwh: float


class DispatchResponse(BaseModel):
    method: str
    profit: float = Field(..., description="Net profit over the horizon ($)")
    energy_charged_mwh: float
    energy_discharged_mwh: float
    schedule: List[Period]


class CompareResponse(BaseModel):
    optimal_profit: float
    rule_based_profit: float
    improvement_pct: float = Field(..., description="Profit gain of the optimal schedule over the rule-based baseline (%)")
    optimal: DispatchResponse
    rule_based: DispatchResponse
