"""Training creates plain JSON forests; no untrusted model deserialization."""
import csv
import hashlib
import io
import json
import math
from datetime import datetime
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import precision_score, recall_score, f1_score, roc_auc_score, brier_score_loss, confusion_matrix
from .schemas import FEATURES,BOUNDS,Observation,utcnow

class ModelError(ValueError):pass

def training_csv(seed=42,rows=1600):
    rng=np.random.default_rng(seed);buffer=io.StringIO();writer=csv.writer(buffer)
    writer.writerow(FEATURES+['event_24h','group_id'])
    for i in range(rows):
        r72=float(rng.uniform(0,900));r24=r72*float(rng.uniform(.08,.95));r3=r24*float(rng.uniform(.03,.7))
        soil=float(rng.uniform(.08,.97));slope=float(rng.uniform(5,65));elevation=float(rng.uniform(50,4500));deform=float(rng.uniform(0,12))
        z=-7+r24/90+r72/600+soil*3.3+slope/24+deform/5
        label=int(rng.random()<1/(1+math.exp(-z)))
        values=[r3,r24,r72,soil,slope,elevation,deform]
        writer.writerow([round(v,5) for v in values]+[label,f'synthetic-block-{i//40:02d}'])
    return buffer.getvalue()

def parse_training(text):
    if len(text.encode())>2_000_000:raise ModelError('Training CSV exceeds 2 MB.')
    reader=csv.DictReader(io.StringIO(text))
    if reader.fieldnames!=FEATURES+['event_24h','group_id']:
        raise ModelError('CSV columns must exactly match the documented feature order, event_24h and group_id.')
    x=[];y=[];groups=[];seen=set()
    for index,row in enumerate(reader):
        if index>=5000:raise ModelError('Training accepts at most 5000 rows.')
        try:
            if None in row or any(v is None for v in row.values()):raise ValueError()
            values=[float(row[k]) for k in FEATURES]
            if any(not math.isfinite(v) or not BOUNDS[k][0]<=v<=BOUNDS[k][1] for k,v in zip(FEATURES,values)):raise ValueError()
            if values[0]>values[1] or values[1]>values[2]:raise ValueError()
            if row['event_24h'] not in {'0','1'}:raise ValueError()
            group=row['group_id'].strip()
            if not group or len(group)>100:raise ValueError()
        except (ValueError,TypeError):raise ModelError(f'Invalid feature, label or group in CSV row {index+2}.') from None
        # Identical feature records cannot leak across holdout groups.
        key=tuple(values)
        if key in seen:raise ModelError('Duplicate feature rows are not allowed; curate duplicate observations before training.')
        seen.add(key);x.append(values);y.append(int(row['event_24h']));groups.append(group)
    if len(x)<100 or len(set(groups))<5:raise ModelError('Provide at least 100 rows across at least 5 independent site/storm groups.')
    if set(y)!={0,1}:raise ModelError('Both event and non-event labels are required.')
    return np.asarray(x),np.asarray(y),np.asarray(groups)

def forest_predict(artifact,values):
    values=np.asarray(values,dtype=np.float32)
    scores=[]
    for tree in artifact['trees']:
        index=0
        while tree['left'][index]!=-1:
            index=tree['left'][index] if values[tree['feature'][index]]<=tree['threshold'][index] else tree['right'][index]
        scores.append(tree['positive_fraction'][index])
    return float(sum(scores)/len(scores))

def train(text,name,provenance='user-supplied-unverified'):
    x,y,groups=parse_training(text)
    train_ids,test_ids=next(GroupShuffleSplit(n_splits=1,test_size=.25,random_state=42).split(x,y,groups))
    if len(set(y[train_ids]))!=2 or len(set(y[test_ids]))!=2:
        raise ModelError('Both classes must occur in the grouped training and holdout partitions. Curate the groups.')
    forest=RandomForestClassifier(n_estimators=60,max_depth=7,min_samples_leaf=4,random_state=42,n_jobs=1)
    forest.fit(x[train_ids],y[train_ids]);prob=forest.predict_proba(x[test_ids])[:,1];pred=prob>=.5
    prevalence=float(np.mean(y[train_ids]));metrics={'precision':float(precision_score(y[test_ids],pred,zero_division=0)),'recall':float(recall_score(y[test_ids],pred,zero_division=0)),'f1':float(f1_score(y[test_ids],pred,zero_division=0)),'roc_auc':float(roc_auc_score(y[test_ids],prob)),'brier':float(brier_score_loss(y[test_ids],prob)),'prevalence_baseline_brier':float(brier_score_loss(y[test_ids],np.full(len(test_ids),prevalence))),'confusion_matrix':confusion_matrix(y[test_ids],pred,labels=[0,1]).tolist(),'holdout_event_prevalence':float(np.mean(y[test_ids]))}
    trees=[]
    for estimator in forest.estimators_:
        t=estimator.tree_;vals=t.value[:,0,:];total=vals.sum(axis=1)
        trees.append({'left':t.children_left.tolist(),'right':t.children_right.tolist(),'feature':t.feature.tolist(),'threshold':t.threshold.tolist(),'positive_fraction':(vals[:,1]/total).tolist()})
    identity=hashlib.sha256((text+'forest-v1').encode()).hexdigest()[:16]
    artifact={'id':identity,'name':name,'created_at':utcnow().isoformat(),'schema':'forest-v1','features':FEATURES,'provenance':provenance,'operationally_validated':False,'dataset_sha256':hashlib.sha256(text.encode()).hexdigest(),'training_rows':len(train_ids),'holdout_rows':len(test_ids),'training_groups':sorted(set(groups[train_ids])),'holdout_groups':sorted(set(groups[test_ids])),'metrics':metrics,'global_importance':dict(zip(FEATURES,forest.feature_importances_.tolist())),'reference_values':dict(zip(FEATURES,np.median(x[train_ids],axis=0).tolist())),'training_ranges':{k:[float(x[train_ids,i].min()),float(x[train_ids,i].max())] for i,k in enumerate(FEATURES)},'trees':trees}
    parity=max(abs(forest_predict(artifact,row)-p) for row,p in zip(x[test_ids][:40],prob[:40]))
    artifact['export_max_error']=parity
    return artifact

def summary(artifact):return {k:v for k,v in artifact.items() if k!='trees'}

def explain(artifact,features):
    values=[features[k] for k in FEATURES];score=forest_predict(artifact,values);drivers=[]
    for i,key in enumerate(FEATURES):
        reference=artifact['reference_values'][key];counter=values.copy();counter[i]=reference
        drivers.append({'feature':key,'value':features[key],'reference':reference,'score_difference':round(score-forest_predict(artifact,counter),5)})
    return score,sorted(drivers,key=lambda d:abs(d['score_difference']),reverse=True)
