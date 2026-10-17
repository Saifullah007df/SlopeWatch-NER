import csv
import io
import numpy as np
import pytest
from slopewatch.models import train,training_csv,parse_training,forest_predict,explain,ModelError
from slopewatch.schemas import FEATURES

def test_model_group_split_and_metrics(model):
    assert not set(model['training_groups'])&set(model['holdout_groups'])
    assert model['export_max_error']<1e-10
    assert model['provenance']=='synthetic' and not model['operationally_validated']
    for key in ['precision','recall','f1','roc_auc','brier','prevalence_baseline_brier']:assert 0<=model['metrics'][key]<=1

def test_reproducibility(model):
    again=train(training_csv(rows=800),'Another display name','synthetic')
    assert again['id']==model['id'] and again['metrics']==model['metrics']

def test_model_response_and_explanation(model):
    low=[2,20,60,.2,38,1600,.2];high=[180,550,850,.94,38,1600,11]
    assert forest_predict(model,high)>forest_predict(model,low)
    score,drivers=explain(model,dict(zip(FEATURES,high)))
    assert 0<=score<=1 and len(drivers)==7

def test_bad_training_schema():
    with pytest.raises(ModelError):parse_training('a,b\n1,2')

def test_training_rejects_duplicate_and_bad_labels():
    text=training_csv(rows=200);lines=text.splitlines()
    with pytest.raises(ModelError):parse_training('\n'.join(lines+[lines[1]]))
    rows=list(csv.reader(io.StringIO(text)));rows[1][-2]='uncertain';buffer=io.StringIO();csv.writer(buffer).writerows(rows)
    with pytest.raises(ModelError):parse_training(buffer.getvalue())

def test_training_requires_groups_and_both_classes():
    rows=list(csv.reader(io.StringIO(training_csv(rows=120))))
    for row in rows[1:]:row[-1]='same'
    buffer=io.StringIO();csv.writer(buffer).writerows(rows)
    with pytest.raises(ModelError):parse_training(buffer.getvalue())
    with pytest.raises(ModelError):parse_training(training_csv(rows=40))

def test_training_rejects_nonfinite():
    rows=list(csv.reader(io.StringIO(training_csv(rows=200))));rows[1][0]='NaN';buffer=io.StringIO();csv.writer(buffer).writerows(rows)
    with pytest.raises(ModelError):parse_training(buffer.getvalue())
