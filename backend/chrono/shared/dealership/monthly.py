"""Reported monthly metric model for Chrono's observed-evidence path.

DealerComposite candidate selection is retained; sampling, intervals, lineage,
admission and goal interpretation remain in the shared engine. This is not a
balanced financial statement and must not be used for underwriting decisions.
"""
import statistics
import numpy as np
from ..domain import FactKind, ModelVersion, digest
from ..model import TrainingFrame


def predict(history, method, horizon):
    if method == 'last-year':
        return history[-12 + horizon % 12]
    if method == 'trend':
        values = history[-6:]
        n = len(values)
        xm, ym = (n - 1) / 2, statistics.mean(values)
        slope = sum((i-xm)*(y-ym) for i,y in enumerate(values)) / sum((i-xm)**2 for i in range(n))
        return ym + slope * (n + horizon - xm)
    return statistics.mean(history[-3:])


class MonthlyMetricModel:
    def __init__(self, metric, unit, signed=False):
        self.metrics = (metric,)
        self.metric, self.unit, self.signed = metric, unit, signed

    def prepare(self, facts):
        selected = sorted((f for f in facts if f.metric == self.metric), key=lambda f:f.valid_at)
        if len(selected) < 6:
            raise ValueError('At least six consecutive completed monthly values are required; no imputation')
        if len(selected) > 240:
            selected = selected[-240:]
        for i,fact in enumerate(selected):
            if fact.kind != FactKind.OBSERVED or fact.unit != self.unit:
                raise ValueError('Only reported observed values in the selected unit are accepted')
            if abs(fact.value) > 1e12 or (not self.signed and fact.value < 0):
                raise ValueError('Monthly values exceed the supported range')
            if i:
                previous = selected[i-1].valid_at
                if fact.valid_at.year*12+fact.valid_at.month - previous.year*12-previous.month != 1:
                    raise ValueError('Monthly values must be contiguous and unique')
        values = np.array([[f.value] for f in selected])
        return TrainingFrame(tuple(f.valid_at for f in selected), values, np.zeros_like(values), tuple(selected))

    def fit(self, data, request):
        if request.horizon > 12 or request.interventions:
            raise ValueError('Reported-metric outlook supports 1–12 months and no generic interventions')
        values = data.values[:,0].tolist()
        methods = ['recent-average'] + (['trend'] if len(values)>=9 else []) + (['last-year'] if len(values)>=18 else [])
        start = max(12 if 'last-year' in methods else 6 if 'trend' in methods else 3,len(values)-6)
        scored=[]
        for method in methods:
            errors=[]
            for i in range(start,len(values)):
                estimate=predict(values[:i],method,0)
                errors.append(values[i]-(estimate if self.signed else max(0,estimate)))
            scored.append((statistics.mean(abs(e) for e in errors),method,errors))
        mae,method,errors=min(scored,key=lambda row:row[0])
        content=dict(family='reported-monthly-metric',implementation='dealer-monthly-chrono-1',
            training_cutoff=request.as_of,knowledge_cutoff=request.known_at,
            data_hash=digest([f.model_dump(mode='json') for f in data.facts]),input_fact_ids=tuple(f.id for f in data.facts),
            parameters=dict(metric=self.metric,unit=self.unit,signed=self.signed,history=values,method=method,
                            selection_mae=mae,selection_months=len(errors),residuals=errors),
            assumptions=('Imported reports are user asserted observations, not independently verified records.',
                         'Candidate selection uses rolling one-month errors; selection MAE is not an independent validation score.',
                         'Centered residual bootstrap accumulates independent monthly innovations; no cross-metric reconciliation.',
                         'Zero historical residuals produce zero simulated variation, not certainty about the future.',
                         'Bands and probabilities describe the selected model, not calibrated real-world confidence.'))
        return ModelVersion(id=digest(content),**content)

    def simulate(self,data,model,request):
        if request.horizon > 12 or request.interventions:
            raise ValueError('Reported-metric outlook supports 1–12 months and no generic interventions')
        p=model.parameters
        if p['metric']!=self.metric or p['unit']!=self.unit or p['signed']!=self.signed or model.data_hash!=digest([f.model_dump(mode='json') for f in data.facts]):
            raise ValueError('Monthly model lineage mismatch')
        rng=np.random.default_rng(request.seed)
        residuals=np.array(p['residuals']);residuals=residuals-residuals.mean()
        innovations=np.cumsum(rng.choice(residuals,size=(request.paths,request.horizon)),axis=1)
        center=np.array([predict(p['history'],p['method'],h) for h in range(request.horizon)])
        paths=center+innovations
        if not self.signed:paths=np.maximum(0,paths)
        return {self.metric:np.column_stack((np.full(request.paths,p['history'][-1]),paths))}
