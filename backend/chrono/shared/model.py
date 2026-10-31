"""Small explicit stock/flow model. Inference is statistical; business mechanics are deterministic."""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from .domain import Fact, ModelVersion, SimulationRequest, digest

Array = NDArray[np.float64]
METRICS = (
    "customers",
    "demand",
    "conversion",
    "retention",
    "capacity",
    "unit_value",
    "gross_margin",
    "fixed_cost",
    "cash",
    "revenue",
)
UNITS = {
    "customers": "count",
    "demand": "count/month",
    "conversion": "fraction",
    "retention": "fraction/month",
    "capacity": "count/month",
    "unit_value": "USD/customer/month",
    "gross_margin": "fraction",
    "fixed_cost": "USD/month",
    "cash": "USD",
    "revenue": "USD/month",
}


def logit(value: Array) -> Array:
    value = np.clip(value, 1e-5, 1 - 1e-5)
    return np.log(value / (1 - value))


def sigmoid(value: Array) -> Array:
    return 1 / (1 + np.exp(-np.clip(value, -30, 30)))


@dataclass(frozen=True)
class TrainingFrame:
    dates: tuple[datetime, ...]
    values: Array
    deviations: Array
    facts: tuple[Fact, ...]


def frame(facts: list[Fact]) -> TrainingFrame:
    rows: dict[datetime, dict[str, Fact]] = {}
    for fact in facts:
        if fact.metric in METRICS:
            if fact.unit != UNITS[fact.metric]:
                raise ValueError(f"invalid unit for {fact.metric}: expected {UNITS[fact.metric]}")
            rows.setdefault(fact.valid_at, {})[fact.metric] = fact
    if len(rows) < 12:
        raise ValueError("insufficient evidence: at least 12 complete monthly observations required")
    dates = tuple(sorted(rows))
    for date, row in rows.items():
        if set(row) != set(METRICS):
            raise ValueError(f"incomplete state at {date.isoformat()}; no silent imputation")
    for before, after in itertools.pairwise(dates):
        if after.year * 12 + after.month - (before.year * 12 + before.month) != 1:
            raise ValueError("observations must be contiguous monthly snapshots")
    ordered = tuple(rows[date][metric] for date in dates for metric in METRICS)
    values = np.array([[rows[date][metric].value for metric in METRICS] for date in dates])
    deviations = np.array([[rows[date][metric].uncertainty.stddev for metric in METRICS] for date in dates])
    if np.any(np.abs(values) > 1e12) or np.any(deviations > 1e12):
        raise ValueError("state exceeds this model's supported numerical range")
    for i, metric in enumerate(METRICS):
        if metric in ("conversion", "retention", "gross_margin"):
            if np.any((values[:, i] < 0) | (values[:, i] > 1)):
                raise ValueError(f"{metric} must be in [0,1]")
        elif metric != "cash" and np.any(values[:, i] < 0):
            raise ValueError(f"{metric} must be nonnegative")
    return TrainingFrame(dates, values, deviations, ordered)


class BusinessModel(Protocol):
    metrics: tuple[str, ...]

    def prepare(self, facts: list[Fact]) -> TrainingFrame: ...

    def fit(self, data: TrainingFrame, request: SimulationRequest) -> ModelVersion: ...
    def simulate(
        self, data: TrainingFrame, model: ModelVersion, request: SimulationRequest
    ) -> dict[str, Array]: ...


class ComputeBackend(Protocol):
    name: str

    def sample(
        self, model: BusinessModel, data: TrainingFrame, version: ModelVersion, request: SimulationRequest
    ) -> dict[str, Array]: ...


class NumpyBackend:
    name = "numpy-pcg64-cpu-v1"

    def sample(
        self, model: BusinessModel, data: TrainingFrame, version: ModelVersion, request: SimulationRequest
    ) -> dict[str, Array]:
        return model.simulate(data, version, request)


class CommercialModel:
    metrics = METRICS

    def prepare(self, facts: list[Fact]) -> TrainingFrame:
        return frame(facts)

    def fit(self, data: TrainingFrame, request: SimulationRequest) -> ModelVersion:
        x = data.values[-13:]
        drivers = np.column_stack((np.log(np.maximum(x[:, 1], 1)), logit(x[:, 2]), logit(x[:, 3])))
        changes = np.diff(drivers, axis=0)
        # Regularized covariance and deliberately conservative shrunk drift, not an LLM forecast.
        empirical = np.cov(changes, rowvar=False)
        covariance = 0.75 * empirical + 0.25 * np.diag(np.diag(empirical))
        covariance += np.diag(np.array([0.025, 0.06, 0.05]) ** 2)
        drift = np.clip(changes.mean(axis=0) * 0.5, [-0.03, -0.04, -0.04], [0.03, 0.04, 0.04])
        parameters = {
            "drift": drift.tolist(),
            "covariance": covariance.tolist(),
            "estimation_samples": len(changes),
            "fit_window": len(x),
            "driver_bounds": [[0, 16], [-10, 10], [-10, 10]],
        }
        ids = tuple(f.id for f in data.facts)
        data_hash = digest([f.model_dump(mode="json") for f in data.facts])
        content = {
            "training_cutoff": request.as_of,
            "knowledge_cutoff": request.known_at,
            "data_hash": data_hash,
            "input_fact_ids": ids,
            "parameters": parameters,
            "assumptions": (
                "Monthly stock/flow model: retained customers plus capacity-limited new wins.",
                "Three transformed drivers follow correlated random walks with shrunk drift.",
                "Approximate drift uncertainty is fixed per path; process innovations vary by month.",
                "Driver floors/bounds and covariance floors are modeling assumptions.",
                "Prices, capacity, costs and margin stay fixed absent an explicit intervention.",
                "Intervention effects are supplied hypotheses, not identified causal estimates.",
                "Insolvency is absorbing; no financing, seasonality or macro shocks are modeled.",
            ),
        }
        return ModelVersion(id=digest({"implementation": "1.0.0", **content}), **content)

    def simulate(
        self, data: TrainingFrame, model: ModelVersion, request: SimulationRequest
    ) -> dict[str, Array]:
        n, h = request.paths, request.horizon
        rng = np.random.Generator(np.random.PCG64(request.seed))
        x = data.values[-1]
        # Measurement uncertainty only affects the latent state used for future transitions.
        initial = rng.normal(x, data.deviations[-1], size=(n, len(METRICS)))
        for i, metric in enumerate(METRICS):
            if metric in ("conversion", "retention", "gross_margin"):
                initial[:, i] = np.clip(initial[:, i], 0, 1)
            elif metric != "cash":
                initial[:, i] = np.maximum(initial[:, i], 0)
        out = {metric: np.empty((n, h + 1)) for metric in METRICS}
        for i, metric in enumerate(METRICS):
            out[metric][:, 0] = x[i]
        covariance = np.array(model.parameters["covariance"])
        drift = rng.multivariate_normal(
            model.parameters["drift"], covariance / model.parameters["estimation_samples"], size=n
        )
        noise = rng.multivariate_normal(np.zeros(3), covariance, size=(h, n))
        driver = np.column_stack(
            (np.log(np.maximum(initial[:, 1], 1)), logit(initial[:, 2]), logit(initial[:, 3]))
        )
        customers, cash = initial[:, 0].copy(), initial[:, 8].copy()
        dead = cash < 0
        effects = {}
        # Independent keyed random streams make paired comparisons invariant to candidate order.
        for action in request.interventions:
            action_seed = int(digest({"seed": request.seed, "id": action.id})[:16], 16)
            action_rng = np.random.Generator(np.random.PCG64(action_seed))
            effects[action.id] = [action_rng.normal(e.mean, e.stddev, n) for e in action.effects]
        for step in range(1, h + 1):
            driver += drift + noise[step - 1]
            driver = np.clip(driver, [0, -10, -10], [16, 10, 10])
            shifted = driver.copy()
            capacity = initial[:, 4].copy()
            cost = np.zeros(n)
            for action in request.interventions:
                age = step - action.start_month
                if 0 <= age < action.duration_months:
                    cost += action.monthly_cost + (action.upfront_cost if age == 0 else 0)
                    for effect, samples in zip(action.effects, effects[action.id]):
                        amount = samples * (1 - action.decay) ** age
                        if effect.driver == "capacity":
                            capacity += amount
                        else:
                            shifted[
                                :, ("demand_log", "conversion_logit", "retention_logit").index(effect.driver)
                            ] += amount
            demand = np.exp(np.clip(shifted[:, 0], 0, 16))
            conversion, retention = sigmoid(shifted[:, 1]), sigmoid(shifted[:, 2])
            capacity = np.maximum(capacity, 0)
            customers = np.where(dead, 0, customers * retention + np.minimum(demand * conversion, capacity))
            revenue = customers * initial[:, 5]
            cash = np.where(dead, cash, cash + revenue * initial[:, 6] - initial[:, 7] - cost)
            dead |= cash < 0
            vals = (
                customers,
                demand,
                conversion,
                retention,
                capacity,
                initial[:, 5],
                initial[:, 6],
                initial[:, 7],
                cash,
                revenue,
            )
            for metric, value in zip(METRICS, vals):
                out[metric][:, step] = value
        return out
