from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import Enum
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator


def now() -> datetime:
    return datetime.now(UTC)


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False).encode()
    ).hexdigest()


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class FactKind(str, Enum):
    OBSERVED = "observed"
    CALCULATED = "calculated"
    INFERRED = "inferred"
    AI_RECONSTRUCTED = "ai_reconstructed"
    FORECAST = "forecast"


class EvidenceScope(str, Enum):
    OWN_COMPANY = "own_company"
    COMPARABLE = "comparable_company"
    INDUSTRY = "industry"
    RESEARCH = "external_research"
    ASSUMPTION = "assumption"


class Evidence(Schema):
    source: str = Field(min_length=1, max_length=500)
    scope: EvidenceScope
    method: str = Field(min_length=1, max_length=2000)
    parent_ids: tuple[str, ...] = ()
    model_id: str | None = None


class Uncertainty(Schema):
    stddev: float = Field(default=0, ge=0)
    interpretation: Literal["measurement", "epistemic", "process"] = "measurement"
    note: str = ""


class Fact(Schema):
    id: str = Field(default_factory=lambda: str(uuid4()), min_length=1)
    entity: str = Field(min_length=1, max_length=100)
    metric: str = Field(min_length=1, max_length=100)
    value: float
    unit: str = Field(min_length=1, max_length=80)
    kind: FactKind
    valid_at: datetime
    recorded_at: datetime = Field(default_factory=now)
    evidence: Evidence
    uncertainty: Uncertainty = Field(default_factory=Uncertainty)
    supersedes: str | None = None

    @model_validator(mode="after")
    def validate_fact(self) -> Fact:
        for stamp in (self.valid_at, self.recorded_at):
            if stamp.utcoffset() is None:
                raise ValueError("timestamps must include a timezone")
        if self.kind == FactKind.OBSERVED and self.valid_at > self.recorded_at:
            raise ValueError("observations cannot describe the future")
        if self.kind != FactKind.OBSERVED and not self.evidence.model_id:
            raise ValueError("derived facts require a model/version identifier")
        if self.kind == FactKind.CALCULATED and not self.evidence.parent_ids:
            raise ValueError("calculated facts require input lineage")
        return self


class Predicate(Schema):
    metric: str
    op: Literal["gte", "lt"]
    value: float


class Region(Schema):
    conditions: tuple[Predicate, ...] = Field(min_length=1)
    match: Literal["all", "any"] = "all"


class Goal(Schema):
    name: str = "Commercial objective"
    target: Region
    outperformance: Region
    failure: Region


class Effect(Schema):
    driver: Literal["demand_log", "conversion_logit", "retention_logit", "capacity"]
    mean: float
    stddev: float = Field(default=0, ge=0)

    @model_validator(mode="after")
    def bounded_effect(self) -> Effect:
        bound = 1e6 if self.driver == "capacity" else 5
        if abs(self.mean) > bound or self.stddev > bound:
            raise ValueError("effect exceeds this model's supported numerical range")
        return self


class Intervention(Schema):
    id: str = Field(min_length=1, max_length=100)
    name: str
    effects: tuple[Effect, ...] = Field(min_length=1, max_length=4)
    evidence: Evidence
    start_month: int = Field(default=1, ge=1, le=60)
    duration_months: int = Field(default=12, ge=1, le=60)
    latest_start_month: int = Field(default=12, ge=1, le=60)
    decay: float = Field(default=0, ge=0, le=1)
    upfront_cost: float = Field(default=0, ge=0)
    monthly_cost: float = Field(default=0, ge=0)

    @model_validator(mode="after")
    def valid_start(self) -> Intervention:
        if self.start_month > self.latest_start_month:
            raise ValueError("intervention starts after its declared decision window")
        return self

    def cost(self, horizon: int) -> float:
        months = max(0, min(self.duration_months, horizon - self.start_month + 1))
        return self.upfront_cost + months * self.monthly_cost if months else 0.0


class SimulationRequest(Schema):
    entity: str = "demo-company"
    as_of: datetime
    known_at: datetime
    horizon: int = Field(default=12, ge=1, le=60)
    paths: int = Field(default=4000, ge=100, le=20000)
    seed: int = Field(default=42, ge=0, le=2**32 - 1)
    goal: Goal
    interventions: tuple[Intervention, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def valid_request(self) -> SimulationRequest:
        if self.as_of.utcoffset() is None or self.known_at.utcoffset() is None:
            raise ValueError("timestamps must include a timezone")
        if len({item.id for item in self.interventions}) != len(self.interventions):
            raise ValueError("intervention IDs must be unique")
        return self


class PlanRequest(Schema):
    simulation: SimulationRequest
    candidates: tuple[Intervention, ...] = Field(max_length=6)
    budget: float = Field(ge=0)
    min_target_probability: float = Field(default=0.7, gt=0, lt=1)
    max_failure_probability: float = Field(default=0.2, gt=0, lt=1)
    max_actions: int = Field(default=2, ge=0, le=3)

    @model_validator(mode="after")
    def bounded_search(self) -> PlanRequest:
        if self.simulation.interventions:
            raise ValueError("plan baseline must have no interventions")
        if len({item.id for item in self.candidates}) != len(self.candidates):
            raise ValueError("candidate IDs must be unique")
        if self.simulation.paths * self.simulation.horizon > 120000:
            raise ValueError("planning work limit: paths * horizon <= 120000")
        return self


class ModelVersion(Schema):
    id: str
    family: str = "commercial-stock-flow"
    implementation: str = "1.0.0"
    training_cutoff: datetime
    knowledge_cutoff: datetime
    data_hash: str
    input_fact_ids: tuple[str, ...]
    parameters: dict
    assumptions: tuple[str, ...]


class Probability(Schema):
    estimate: float = Field(ge=0, le=1)
    lower: float = Field(ge=0, le=1)
    upper: float = Field(ge=0, le=1)


class Band(Schema):
    low: list[float]
    median: list[float]
    high: list[float]


class SimulationResult(Schema):
    run_id: str
    model_id: str
    request: SimulationRequest
    backend: str
    runtime: dict[str, str]
    origin: datetime
    input_fact_ids: tuple[str, ...]
    data_hash: str
    bands: dict[str, Band]
    probabilities: dict[str, list[Probability]]
    corridors: dict[str, dict[str, Band] | None]
    terminal_expected: dict[str, float]
    warnings: tuple[str, ...]


class BacktestRequest(Schema):
    entity: str = "demo-company"
    goal: Goal
    evaluation_known_at: datetime
    horizon: int = Field(default=3, ge=1, le=12)
    min_train: int = Field(default=18, ge=12)
    max_folds: int = Field(default=60, ge=1, le=120)
    paths: int = Field(default=1000, ge=100, le=4000)
    seed: int = Field(default=42, ge=0, le=2**32 - 1)

    @model_validator(mode="after")
    def aware_cutoff(self) -> BacktestRequest:
        if self.evaluation_known_at.utcoffset() is None:
            raise ValueError("evaluation_known_at must include a timezone")
        return self


FactBatch = Annotated[list[Fact], Field(min_length=1, max_length=2000)]


class PlanCandidate(Schema):
    actions: list[str]
    cost: float
    feasible: bool
    target: Probability
    failure: Probability
    outperformance: Probability | None = None
    target_probability_delta: float
    expected_net_cash_delta: float
    paired_cash_delta_mc_standard_error: float


class StrategicDelta(Schema):
    metric: str
    required: float
    op: Literal["gte", "lt"]
    baseline_median: float
    absolute_gap: float
    relative_gap: float


class PlanResult(Schema):
    run_id: str
    model_id: str
    request: PlanRequest
    data_hash: str
    input_fact_ids: list[str]
    backend: str
    runtime: dict[str, str]
    status: Literal["feasible_in_candidate_set", "no_feasible_plan_in_candidate_set"]
    selected: PlanCandidate
    evaluated: list[PlanCandidate]
    strategic_delta: list[StrategicDelta]
    illustrative_successful_path: dict[str, list[float]] | None
    notes: list[str]


class OutcomeImpact(Schema):
    current_target_probability: float
    prior_level_target_probability: float
    probability_delta: float
    method: str


class InflectionEvent(Schema):
    detected_at: datetime
    metric: str
    category: Literal[
        "unknown", "internal", "market", "economic", "technological", "regulatory", "behavioral"
    ]
    category_status: str
    prior_mean: float
    recent_mean: float
    delta: float
    screening_statistic: float
    persistence: float
    confidence: float | None
    confidence_note: str
    evidence_ids: list[str]
    outcome_impact: OutcomeImpact | None
    actionability: float | None
    decision_window: str | None


class InflectionResult(Schema):
    run_id: str
    model_id: str
    request: SimulationRequest
    events: list[InflectionEvent]
    notes: list[str]


class BacktestFold(Schema):
    origin: datetime
    target_date: datetime
    model_id: str
    training_data_hash: str
    max_training_recorded_at: datetime
    actual: float
    median: float
    low: float
    high: float
    naive: float
    covered: bool
    crps: float
    interval_score: float
    probabilities: dict[str, float]
    outcomes: dict[str, int]


class BacktestMetrics(Schema):
    mae: float
    rmse: float
    naive_rmse: float
    coverage_80: float
    mean_crps: float
    mean_interval_score: float
    brier: dict[str, float]


class CalibrationBin(Schema):
    bin_low: float = Field(ge=0, lt=1)
    bin_high: float = Field(gt=0, le=1)
    count: int = Field(ge=1)
    mean_prediction: float = Field(ge=0, le=1)
    observed_frequency: float = Field(ge=0, le=1)


class SkippedFold(Schema):
    origin: datetime
    reason: str


class BacktestResult(Schema):
    run_id: str
    request: BacktestRequest
    folds: list[BacktestFold]
    skipped: list[SkippedFold]
    metrics: BacktestMetrics
    target_calibration: list[CalibrationBin]
    corridor_calibration: dict[Literal["target", "outperformance", "failure"], list[CalibrationBin]] | None = None
    evaluation_data_hash: str
    notes: list[str]

    @model_validator(mode="after")
    def complete_calibration(self):
        if self.corridor_calibration is not None:
            if set(self.corridor_calibration) != {"target", "outperformance", "failure"}:
                raise ValueError("Calibration must cover all three corridors")
            if self.corridor_calibration["target"] != self.target_calibration:
                raise ValueError("Target calibration must match the target corridor")
            if any(sum(bin.count for bin in bins) != len(self.folds) for bins in self.corridor_calibration.values()):
                raise ValueError("Each corridor must account for every completed fold")
        return self

    @model_serializer(mode="wrap")
    def preserve_prior_results(self, handler):
        result = handler(self)
        if self.corridor_calibration is None:
            result.pop("corridor_calibration", None)
        return result
