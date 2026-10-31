"""Dealer terminology and stock/flow mechanics as a Chrono model plugin.

Paired scenarios use the same trial/seed streams. Bands, outcome regions,
probability intervals, numerical validation and admission belong to Chrono.
No independent Composite execution, forecasting, or backtesting service.
"""
from dataclasses import dataclass
from copy import deepcopy
import numpy as np

from ..domain import ModelVersion, SimulationRequest, digest
from ..model import TrainingFrame
from .model import validate, simulate_one, MODEL_VERSION
from .earnings import cashflow
from .workflow import require_ready


METRICS = ('sales', 'leads', 'gross', 'contribution', 'revenue', 'fi_gross', 'service_ros', 'service_gross',
           'holding_cost', 'payroll', 'overhead', 'unhandled_leads', 'stock_lost_sales', 'profit', 'cash')


@dataclass(frozen=True)
class DealershipFrame(TrainingFrame):
    inputs: dict


class DealershipModel:
    metrics = METRICS

    def prepare(self, facts):
        raise ValueError('Use explicit assumption scenarios. Historical calibration is not implemented for this domain model.')

    def prepare_assumptions(self, inputs: dict, request: SimulationRequest) -> DealershipFrame:
        if request.paths > 200 or request.horizon > 36:
            raise ValueError('Dealership execution limit: 100–200 paths and 1–36 months')
        e = validate({**deepcopy(inputs), 'months': request.horizon, 'trials': request.paths, 'seed': request.seed})
        require_ready(e)
        if not e['operating_enabled']:
            raise ValueError('Include payroll and operating costs before evaluating profit and cash')
        return DealershipFrame((request.as_of,), np.zeros((1, len(METRICS))), np.zeros((1, len(METRICS))), (), e)

    def fit(self, data: DealershipFrame, request: SimulationRequest) -> ModelVersion:
        content = dict(family='dealership-assumptions', implementation=MODEL_VERSION + '-chrono-1',
                       training_cutoff=request.as_of, knowledge_cutoff=request.known_at,
                       data_hash=digest(data.inputs), input_fact_ids=(),
                       parameters={'basis': 'explicit_assumptions', 'input': deepcopy(data.inputs)},
                       assumptions=('No historical fit or external forecast calibration is performed.',
                                    'Dealer Composite 5.4.0 domain mechanics; Chrono sampling and outcome summaries.',
                                    'Flow metrics are cumulative since scenario origin; cash is a balance.',
                                    'Scenario inputs and dated reference defaults require review; they are not observed facts.'))
        return ModelVersion(id=digest(content), **content)

    def simulate(self, data: DealershipFrame, model: ModelVersion, request: SimulationRequest):
        if request.interventions:
            raise ValueError('Generic commercial interventions are not supported by the dealership model')
        e = model.parameters['input']
        if digest(e) != model.data_hash or digest(data.inputs) != model.data_hash:
            raise ValueError('Model input lineage mismatch')
        outputs = {k: np.zeros((request.paths, request.horizon + 1)) for k in METRICS}
        for trial in range(request.paths):
            rows = simulate_one(e, 'scenario', trial)
            financial = cashflow(rows, e, 'scenario')
            for metric in METRICS:
                if metric == 'cash':
                    outputs[metric][trial] = [e['finance']['scenario']['opening_cash'], *[m['cash_balance'] for m in financial]]
                else:
                    values = [m['profit'] for m in financial] if metric == 'profit' else [m['vehicle_revenue' if metric == 'revenue' else metric] for m in rows]
                    outputs[metric][trial, 1:] = np.cumsum(values)
        return outputs
