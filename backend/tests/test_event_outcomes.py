import pytest
from core import event_outcomes
from core.dealeros import ledger
from core.entities import Entity
from api.routers import campaign_workflow as workflow
@pytest.fixture(autouse=True)
def isolate():
 ledger.reset();yield;ledger.reset()
def test_event_outcomes_only_count_explicit_completed_links_once(monkeypatch):
 rows=[{'campaign_id':'C1','outcome_id':'D1','stage':'sale_completed','recorded_value':12345.67,'currency':'USD'}, {'campaign_id':'C1','outcome_id':'D1','stage':'sale_completed','recorded_value':12345.67,'currency':'USD'}, {'campaign_id':'C1','outcome_id':'S1','stage':'service_completed','recorded_value':150,'currency':'CAD'}, {'campaign_id':'C1','outcome_id':'S2','stage':'service_completed','recorded_value':None,'currency':None}, {'campaign_id':'C1','stage':'response_due','closed':False}, {'campaign_id':'C2','outcome_id':'D2','stage':'sale_completed','recorded_value':999,'currency':'USD'}]
 for i,row in enumerate(rows):ledger.add_entity(Entity(str(i),workflow.CASE,row))
 monkeypatch.setattr(workflow,'projection',lambda e:e.attributes)
 result=event_outcomes.summarize_event_outcomes({'C1'})
 assert result['responses']==5
 assert result['completed_outcomes']==3
 assert result['values_by_currency']=={'USD':12345.67,'CAD':150}
 assert result['missing_values']==1
 assert result['follow_up_due']==1
 assert event_outcomes.summarize_event_outcomes(set())['completed_outcomes']==0
