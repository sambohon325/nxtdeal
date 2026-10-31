"""Explicit assumption scenarios over the same sampling and outcome engine.

This path never manufactures observed facts to satisfy the historical-fit path.
Callers supply a versioned domain model and their own authorized repository.
"""
from .compute_admission import admitted
from .domain import SimulationRequest, SimulationResult
from .engine import Engine, band, probability
from uuid import uuid4
import numpy as np


class AssumptionEngine(Engine):
    @admitted
    def simulate_assumptions(self, request: SimulationRequest, inputs: dict) -> SimulationResult:
        result, _ = self._evaluate_assumptions(request, inputs)
        return result

    @admitted
    def compare_assumptions(self, request: SimulationRequest, baseline: dict, proposed: dict) -> dict:
        """Paired trial deltas; never subtract unrelated percentile summaries."""
        before, a = self._evaluate_assumptions(request, baseline)
        after, b = self._evaluate_assumptions(request, proposed)
        result = dict(run_id=str(uuid4()), request=request.model_dump(mode='json'),
                      baseline=before.model_dump(mode='json'), proposed=after.model_dump(mode='json'),
                      expected_series={'baseline':{key:np.mean(values,axis=0).tolist() for key,values in a.items()},
                                       'proposed':{key:np.mean(values,axis=0).tolist() for key,values in b.items()}},
                      difference={key: band(b[key] - a[key]).model_dump(mode='json') for key in self.model.metrics},
                      probability_positive={key: probability((b[key] - a[key])[:, -1] > 0).model_dump(mode='json') for key in self.model.metrics},
                      basis='Paired explicit assumption scenarios; positive is an arithmetic increase, not always a desirable business outcome.')
        self.repository.save_run(result['run_id'], 'assumption_comparison', result)
        return result

    def _evaluate_assumptions(self, request: SimulationRequest, inputs: dict):
        if request.interventions:
            raise ValueError('Use the domain model inputs for assumption scenarios; generic interventions are not applied.')
        prepare = getattr(self.model, 'prepare_assumptions', None)
        if prepare is None:
            raise ValueError('This model does not support explicit assumption scenarios')
        data = prepare(inputs, request)
        if data.facts:
            raise ValueError('Assumption scenarios cannot manufacture training facts')
        for region in (request.goal.target, request.goal.outperformance, request.goal.failure):
            if any(c.metric not in self.model.metrics for c in region.conditions):
                raise ValueError('Unsupported goal metric')
        version = self.model.fit(data, request)
        if version.input_fact_ids:
            raise ValueError('Assumption scenarios must retain input lineage as assumptions, not facts')
        self.repository.save_model(version)
        paths = self.sample(data, version, request)
        result = self.summarize(request, data, version, paths)
        result = result.model_copy(update={'warnings': tuple(
            w for w in result.warnings
            if w != "No inferred or AI-reconstructed facts are admitted to this model's training data."
        ) + (
            'Explicit assumption scenario, not a historical-data forecast. No observed training facts were created.',
            'User-reported inputs remain unverified. Game progression and cosmetic rewards have no effect on results.',
        )})
        self.repository.save_run(result.run_id, 'assumption_scenario', result.model_dump(mode='json'))
        return result, paths
