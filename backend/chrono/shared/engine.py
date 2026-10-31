from __future__ import annotations

import itertools
import platform
from typing import Protocol
from uuid import uuid4

import numpy as np

from .compute_admission import admitted
from .domain import (
    Band,
    FactKind,
    ModelVersion,
    PlanRequest,
    PlanResult,
    Probability,
    Region,
    SimulationRequest,
    SimulationResult,
)
from .model import (
    Array,
    BusinessModel,
    CommercialModel,
    ComputeBackend,
    NumpyBackend,
    TrainingFrame,
)
from .store import TemporalRepository


class HypothesisProvider(Protocol):
    """An LLM/research model may propose typed hypotheses; it cannot write observed facts or execute actions."""

    def propose(self, evidence: tuple[dict, ...], output_schema: dict) -> dict: ...


class ActionAdapter(Protocol):
    """Future execution boundary. Implementations must enforce approval, idempotency and reconciliation."""

    def execute(self, approved_command: dict, idempotency_key: str) -> dict: ...


def region_mask(region: Region, paths: dict[str, Array]) -> np.ndarray:
    masks = []
    for condition in region.conditions:
        if condition.metric not in paths:
            raise ValueError(f"unsupported goal metric: {condition.metric}")
        value = paths[condition.metric]
        masks.append(value >= condition.value if condition.op == "gte" else value < condition.value)
    return np.logical_and.reduce(masks) if region.match == "all" else np.logical_or.reduce(masks)


def membership(request: SimulationRequest, paths: dict[str, Array]) -> dict[str, np.ndarray]:
    failure = region_mask(request.goal.failure, paths)
    # Failure takes precedence. Target attainment includes outperformance only if target predicates hold.
    target = region_mask(request.goal.target, paths) & ~failure
    upside = region_mask(request.goal.outperformance, paths) & target
    return {
        "outperformance": upside,
        "target": target,
        "failure": failure,
        "target_only": target & ~upside,
        "shortfall": ~(failure | target),
    }


def probability(mask: np.ndarray) -> Probability:
    n = len(mask)
    p = float(np.mean(mask))
    z = 1.959963984540054
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return Probability(estimate=p, lower=max(0, float(center - half)), upper=min(1, float(center + half)))


def band(values: Array) -> Band:
    low, median, high = np.quantile(values, [0.1, 0.5, 0.9], axis=0)
    return Band(low=low.tolist(), median=median.tolist(), high=high.tolist())


class Engine:
    def __init__(
        self,
        repository: TemporalRepository,
        model: BusinessModel | None = None,
        backend: ComputeBackend | None = None,
    ):
        self.repository = repository
        self.model = model or CommercialModel()
        self.backend = backend or NumpyBackend()

    def sample(
        self, data: TrainingFrame, model: ModelVersion, request: SimulationRequest
    ) -> dict[str, Array]:
        """Validate every replaceable backend result before interpreting its samples."""
        paths = self.backend.sample(self.model, data, model, request)
        if not isinstance(paths, dict) or set(paths) != set(self.model.metrics):
            raise ValueError("Compute backend must return exactly the declared model metrics")
        expected = (request.paths, request.horizon + 1)
        checked = {}
        for metric, values in paths.items():
            if (
                not isinstance(values, np.ndarray)
                or np.ma.isMaskedArray(values)
                or values.shape != expected
                or not (
                    np.issubdtype(values.dtype, np.floating)
                    or np.issubdtype(values.dtype, np.integer)
                )
            ):
                raise ValueError(
                    f"Compute backend metric {metric} must be a real numeric array of shape {expected}"
                )
            try:
                with np.errstate(over="raise", invalid="raise"):
                    values = values.astype(np.float64, copy=True)
            except FloatingPointError as error:
                raise ValueError(f"Compute backend metric {metric} exceeds float64 range") from error
            if not np.all(np.isfinite(values)):
                raise ValueError(f"Compute backend metric {metric} contains nonfinite samples")
            checked[metric] = values
        return checked

    def prepare(self, request: SimulationRequest) -> tuple[TrainingFrame, ModelVersion]:
        facts = self.repository.history(request.entity, request.as_of, request.known_at, FactKind.OBSERVED)
        data = self.model.prepare(facts)
        if (request.as_of - data.dates[-1]).total_seconds() > 32 * 86400:
            raise ValueError("latest observed state is stale by more than 32 days")
        for region in (request.goal.target, request.goal.outperformance, request.goal.failure):
            for condition in region.conditions:
                if condition.metric not in self.model.metrics:
                    raise ValueError(f"unsupported goal metric: {condition.metric}")
        version = self.model.fit(data, request)
        self.repository.save_model(version)
        return data, version

    def summarize(
        self, request: SimulationRequest, data: TrainingFrame, model: ModelVersion, paths: dict[str, Array]
    ) -> SimulationResult:
        masks = membership(request, paths)
        probabilities = {
            name: [probability(mask[:, t]) for t in range(request.horizon + 1)]
            for name, mask in masks.items()
        }
        corridors = {}
        for name in ("outperformance", "target", "failure"):
            chosen = masks[name][:, -1]
            corridors[name] = (
                {metric: band(values[chosen]) for metric, values in paths.items()} if np.any(chosen) else None
            )
        warnings = [
            "Synthetic/demo mechanics are not externally validated business predictions.",
            "Probability intervals measure Monte Carlo sampling error, not model correctness.",
            "Bands are marginal 10th–90th percentiles, not simultaneous path guarantees.",
            "Corridors condition on terminal goal membership; target includes outperformance.",
            "No inferred or AI-reconstructed facts are admitted to this model's training data.",
        ]
        if request.known_at > request.as_of:
            warnings.append(
                "Retrospective knowledge view: known_at exceeds as_of; do not use as a backtest forecast."
            )
        if request.horizon > 24:
            warnings.append("Long horizon extrapolation is especially sensitive to structural assumptions.")
        for name in corridors:
            if masks[name][:, -1].sum() < 30:
                warnings.append(f"Sparse {name} corridor: fewer than 30 terminal members.")
        return SimulationResult(
            run_id=str(uuid4()),
            model_id=model.id,
            request=request,
            backend=self.backend.name,
            runtime={"python": platform.python_version(), "numpy": np.__version__},
            origin=data.dates[-1],
            input_fact_ids=model.input_fact_ids,
            data_hash=model.data_hash,
            bands={metric: band(value) for metric, value in paths.items()},
            probabilities=probabilities,
            corridors=corridors,
            terminal_expected={metric: float(np.mean(value[:, -1])) for metric, value in paths.items()},
            warnings=tuple(warnings),
        )

    @admitted
    def simulate(self, request: SimulationRequest) -> SimulationResult:
        data, model = self.prepare(request)
        paths = self.sample(data, model, request)
        result = self.summarize(request, data, model, paths)
        self.repository.save_run(result.run_id, "simulation", result.model_dump(mode="json"))
        return result

    @admitted
    def plan(self, request: PlanRequest) -> dict:
        base = request.simulation
        data, model = self.prepare(base)
        baseline_paths = self.sample(data, model, base)
        baseline_masks = membership(base, baseline_paths)
        evaluated = []
        best_paths = None
        best_key = None
        for size in range(request.max_actions + 1):
            for actions in itertools.combinations(request.candidates, size):
                cost = sum(action.cost(base.horizon) for action in actions)
                if cost > request.budget:
                    continue
                scenario = base.model_copy(update={"interventions": actions})
                paths = (
                    baseline_paths if not actions else self.sample(data, model, scenario)
                )
                masks = membership(scenario, paths)
                target, failure = probability(masks["target"][:, -1]), probability(masks["failure"][:, -1])
                feasible = (
                    target.lower >= request.min_target_probability
                    and failure.upper <= request.max_failure_probability
                )
                paired_cash = paths["cash"][:, -1] - baseline_paths["cash"][:, -1]
                entry = {
                    "actions": [action.id for action in actions],
                    "cost": cost,
                    "feasible": feasible,
                    "target": target.model_dump(),
                    "failure": failure.model_dump(),
                    "outperformance": probability(masks["outperformance"][:, -1]).model_dump(),
                    "target_probability_delta": float(
                        masks["target"][:, -1].mean() - baseline_masks["target"][:, -1].mean()
                    ),
                    "expected_net_cash_delta": float(paired_cash.mean()),
                    "paired_cash_delta_mc_standard_error": float(
                        paired_cash.std(ddof=1) / np.sqrt(base.paths)
                    ),
                }
                evaluated.append(entry)
                key = (not feasible, cost if feasible else -target.lower, -float(paired_cash.mean()))
                if best_key is None or key < best_key:
                    best_key, best_paths, best_entry = key, paths, entry
        assert best_paths is not None
        masks = membership(base, best_paths)
        successful = np.flatnonzero(masks["target"][:, -1])
        milestones = None
        if len(successful):
            # Select a real successful sample near the terminal median, not an impossible average path.
            revenues = best_paths["revenue"][successful, -1]
            representative = successful[np.argmin(np.abs(revenues - np.median(revenues)))]
            milestones = {metric: values[representative].tolist() for metric, values in best_paths.items()}
        gaps = []
        for condition in base.goal.target.conditions:
            projected = float(np.median(baseline_paths[condition.metric][:, -1]))
            gap = (
                max(0, condition.value - projected)
                if condition.op == "gte"
                else max(0, projected - condition.value)
            )
            gaps.append(
                {
                    "metric": condition.metric,
                    "required": condition.value,
                    "op": condition.op,
                    "baseline_median": projected,
                    "absolute_gap": gap,
                    "relative_gap": gap / max(abs(condition.value), 1),
                }
            )
        result = {
            "run_id": str(uuid4()),
            "model_id": model.id,
            "request": request.model_dump(mode="json"),
            "data_hash": model.data_hash,
            "input_fact_ids": list(model.input_fact_ids),
            "backend": self.backend.name,
            "runtime": {"python": platform.python_version(), "numpy": np.__version__},
            "status": "feasible_in_candidate_set"
            if best_entry["feasible"]
            else "no_feasible_plan_in_candidate_set",
            "selected": best_entry,
            "evaluated": evaluated,
            "strategic_delta": gaps,
            "illustrative_successful_path": milestones,
            "notes": [
                "Exhaustive bounded subset search; not global reachability or causal proof.",
                "Success and risk constraints use Wilson Monte Carlo bounds.",
                "Intervention costs are charged to cash; paired simulations share random numbers.",
                "Milestones illustrate one successful sample, not a guaranteed route.",
                "Action windows and effect distributions are declared assumptions.",
            ],
        }
        result = PlanResult.model_validate(result).model_dump(mode="json")
        self.repository.save_run(result["run_id"], "plan", result)
        return result
