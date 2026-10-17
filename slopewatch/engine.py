import json
from datetime import datetime,timedelta
from uuid import uuid4
from .schemas import Observation,Zone,FEATURES,utcnow
from .models import train,training_csv,explain,summary

class DomainError(ValueError):pass
BANDS=['Low','Moderate','High','Critical']
def band(score):return 'Low' if score<.30 else 'Moderate' if score<.60 else 'High' if score<.85 else 'Critical'
def quality(observation,zone,now=None):
    now=now or utcnow();age=(now-observation.observed_at).total_seconds();reasons=[]
    for key in FEATURES:
        if (getattr(observation,key,None) if key not in {'slope_deg','elevation_m'} else zone.get(key)) is None:reasons.append(f'Missing {key}')
    if age>3600:reasons.append('Observation is older than 60 minutes')
    if age < -300:reasons.append('Observation is more than 5 minutes in the future')
    return {'passed':not reasons,'age_minutes':round(age/60,2),'reasons':reasons}

def bootstrap(store):
    if store.rows('zones'):return
    model=train(training_csv(),'Synthetic baseline RF','synthetic')
    seed=[('gangtok','Gangtok','Sikkim',27.3314,88.6138,38,1650),('haflong','Haflong','Assam',25.1648,93.0176,31,680),('shillong','Shillong','Meghalaya',25.5788,91.8933,29,1496),('aizawl','Aizawl','Mizoram',23.7271,92.7176,42,1132),('kohima','Kohima','Nagaland',25.6751,94.1086,35,1444),('imphal','Imphal','Manipur',24.8170,93.9368,22,790),('itanagar','Itanagar','Arunachal Pradesh',27.0844,93.6053,37,320),('agartala','Agartala','Tripura',23.8315,91.2868,19,100)]
    with store.transaction() as c:
        if c.execute('SELECT 1 FROM zones').fetchone():return
        c.execute('INSERT INTO models(id,data,active) VALUES(?,?,1)',(model['id'],json.dumps(model)))
        for key,name,state,lat,lon,slope,elev in seed:
            z=Zone(id=key,name=name+' demonstration slope',state=state,latitude=lat,longitude=lon,slope_deg=slope,elevation_m=elev,terrain_source='synthetic-fixture').model_dump()
            c.execute('INSERT INTO zones VALUES(?,?)',(key,json.dumps(z)))
        store.audit(c,'workspace_initialized',{'mode':'synthetic','zones':8,'model_id':model['id']})
    now=utcnow()
    for index,(key,*_) in enumerate(seed):
        mode=['intense-storm','rainfall-rise','quiet','intense-storm','rainfall-rise','quiet','missing-sensor','stale-reading'][index]
        for n in range(6):
            at=now-timedelta(minutes=50-n*8)
            if mode=='stale-reading':at-=timedelta(hours=3)
            ingest(store,scenario_observation(key,mode,at),now=now)

def scenario_observation(zone_id,mode,at=None):
    values={'quiet':(4,22,65,.25,.15),'rainfall-rise':(70,230,430,.77,4),'intense-storm':(180,550,850,.94,11),'missing-sensor':(100,300,600,None,6),'stale-reading':(80,280,560,.8,5)}[mode]
    when=at or (utcnow()-timedelta(hours=3) if mode=='stale-reading' else utcnow())
    return Observation(zone_id=zone_id,observed_at=when,source='synthetic',rain_3h_mm=values[0],rain_24h_mm=values[1],rain_72h_mm=values[2],soil_moisture=values[3],deformation_mm_day=values[4],note='Synthetic scenario: '+mode)

def _assessment(c,store,observation,now):
    row=c.execute('SELECT data FROM zones WHERE id=?',(observation.zone_id,)).fetchone()
    if not row:raise DomainError('Unknown monitoring zone.')
    zone=json.loads(row['data']);when=observation.observed_at.isoformat();data=observation.model_dump(mode='json')
    old=c.execute('SELECT id,data FROM observations WHERE zone_id=? AND observed_at=?',(observation.zone_id,when)).fetchone()
    if old:
        if json.loads(old['data'])!=data:raise DomainError('A different observation already exists at this zone and timestamp.')
        assessment=c.execute('SELECT data FROM assessments WHERE observation_id=?',(old['id'],)).fetchone()
        return dict(json.loads(assessment['data']),duplicate=True)
    latest=c.execute('SELECT observed_at FROM observations WHERE zone_id=? ORDER BY observed_at DESC LIMIT 1',(observation.zone_id,)).fetchone()
    if latest and when<latest['observed_at']:raise DomainError('Out-of-order readings are rejected. Import new observations in chronological order per zone.')
    if (observation.observed_at-now).total_seconds()>300:raise DomainError('Observation timestamp is more than five minutes ahead.')
    q=quality(observation,zone,now);model=store.active_model(c)
    features={key:zone[key] if key in {'slope_deg','elevation_m'} else getattr(observation,key) for key in FEATURES}
    score=None;drivers=[];outliers=[]
    if q['passed']:
        score,drivers=explain(model,features)
        outliers=[key for key in FEATURES if not model['training_ranges'][key][0]<=features[key]<=model['training_ranges'][key][1]]
    observation_id=uuid4().hex
    assessment={'id':uuid4().hex,'observation_id':observation_id,'zone_id':observation.zone_id,'observed_at':when,'created_at':now.isoformat(),'source':observation.source,'terrain_source':zone['terrain_source'],'model_id':model['id'],'model_name':model['name'],'model_provenance':model['provenance'],'operationally_validated':False,'score':round(score,5) if score is not None else None,'band':band(score) if score is not None else 'Unknown','quality':q,'features':features,'drivers':drivers,'outside_training_range':outliers,'score_meaning':'Synthetic model score' if model['provenance']=='synthetic' else 'Unvalidated research model score','note':observation.note}
    c.execute('INSERT INTO observations VALUES(?,?,?,?)',(observation_id,observation.zone_id,when,json.dumps(data)))
    c.execute('INSERT INTO assessments VALUES(?,?,?,?)',(assessment['id'],observation_id,observation.zone_id,json.dumps(assessment)))
    row=c.execute('SELECT high,clear FROM counters WHERE zone_id=?',(observation.zone_id,)).fetchone();high,clear=(row['high'],row['clear']) if row else (0,0)
    if latest and (observation.observed_at-datetime.fromisoformat(latest['observed_at'])).total_seconds()>3600:
        high,clear=0,0
    high=high+1 if score is not None and score>=.60 else 0
    clear=clear+1 if score is not None and score<.45 else 0
    row=c.execute("SELECT data FROM episodes WHERE zone_id=? AND status!='closed'",(observation.zone_id,)).fetchone();ep=json.loads(row['data']) if row else None
    if not ep and high>=2:
        ep={'id':uuid4().hex,'zone_id':observation.zone_id,'opened_at':now.isoformat(),'status':'open','severity':assessment['band'],'condition_resolved':False,'latest_assessment_id':assessment['id'],'model_id':model['id'],'acknowledgement':None,'closure':None,'resolved_at':None}
        c.execute('INSERT INTO episodes VALUES(?,?,?,?)',(ep['id'],observation.zone_id,ep['status'],json.dumps(ep)))
        store.audit(c,'episode_opened',{'episode_id':ep['id'],'zone_id':ep['zone_id'],'assessment_id':assessment['id']})
    elif ep:
        ep['latest_assessment_id']=assessment['id']
        if score is not None and score>=.45:
            if ep['condition_resolved'] and score>=.60:
                ep['status']='open';ep['acknowledgement']=None
            ep['condition_resolved']=False;ep['resolved_at']=None
        if score is not None and score>=.85 and ep['severity']!='Critical':
            ep['severity']='Critical';ep['status']='open';ep['acknowledgement']=None
            store.audit(c,'episode_escalated',{'episode_id':ep['id'],'assessment_id':assessment['id']})
        if clear>=2 and not ep['condition_resolved']:
            ep['condition_resolved']=True;ep['resolved_at']=now.isoformat()
            store.audit(c,'condition_resolved',{'episode_id':ep['id'],'assessment_id':assessment['id']})
        if score is None:
            # Loss of evidence invalidates a previous clearance until fresh evidence returns.
            ep['condition_resolved']=False;ep['resolved_at']=None
        c.execute('UPDATE episodes SET status=?,data=? WHERE id=?',(ep['status'],json.dumps(ep),ep['id']))
    c.execute('INSERT INTO counters VALUES(?,?,?) ON CONFLICT(zone_id) DO UPDATE SET high=excluded.high,clear=excluded.clear',(observation.zone_id,high,clear))
    store.audit(c,'observation_assessed',{'zone_id':observation.zone_id,'assessment_id':assessment['id'],'band':assessment['band'],'source':observation.source,'model_id':model['id']})
    return dict(assessment,duplicate=False)

def ingest(store,observation,now=None):
    with store.transaction() as c:return _assessment(c,store,observation,now or utcnow())
def ingest_batch(store,observations):
    now=utcnow()
    with store.transaction() as c:return [_assessment(c,store,item,now) for item in observations]

def snapshot(store):
    with store.connect() as c:
        zones=[];now=utcnow()
        for row in c.execute('SELECT data FROM zones ORDER BY id'):
            zone=json.loads(row['data']);last=c.execute('SELECT data FROM assessments WHERE zone_id=? ORDER BY rowid DESC LIMIT 1',(zone['id'],)).fetchone()
            assessment=json.loads(last['data']) if last else None
            if assessment:
                obs=c.execute('SELECT data FROM observations WHERE id=?',(assessment['observation_id'],)).fetchone()
                q=quality(Observation.model_validate_json(obs['data']),zone,now)
                assessment=dict(assessment,current_quality=q)
                if not q['passed']:assessment=dict(assessment,score=None,band='Unknown')
            zones.append(dict(zone,latest=assessment))
        model=summary(store.active_model(c))
    episodes=store.rows('episodes');deliveries=store.rows('deliveries')
    return {'generated_at':now.isoformat(),'zones':zones,'episodes':episodes,'deliveries':deliveries,'active_model':model,'mode':'research-only','notices':['Demonstration locations and terrain are synthetic fixtures, not deployed sensors.','Scores are not calibrated event probabilities. No real messages are sent.']}

def episode_action(store,episode_id,action,note):
    with store.transaction() as c:
        row=c.execute('SELECT data FROM episodes WHERE id=?',(episode_id,)).fetchone()
        if not row:raise DomainError('Episode not found.')
        ep=json.loads(row['data'])
        if ep['status']=='closed':raise DomainError('This episode is already closed.')
        if action=='acknowledge':
            ep['status']='acknowledged';ep['acknowledgement']={'note':note,'at':utcnow().isoformat(),'actor':'local-user'}
        elif action=='close':
            if not ep['acknowledgement'] or not ep['condition_resolved']:raise DomainError('Acknowledge the episode and obtain two fresh clearance observations before closure.')
            latest=c.execute('SELECT data FROM assessments WHERE zone_id=? ORDER BY rowid DESC LIMIT 1',(ep['zone_id'],)).fetchone()
            a=json.loads(latest['data']);o=c.execute('SELECT data FROM observations WHERE id=?',(a['observation_id'],)).fetchone();z=c.execute('SELECT data FROM zones WHERE id=?',(ep['zone_id'],)).fetchone()
            counter=c.execute('SELECT clear FROM counters WHERE zone_id=?',(ep['zone_id'],)).fetchone()
            if not quality(Observation.model_validate_json(o['data']),json.loads(z['data']))['passed'] or a['score'] is None or a['score']>=.45 or counter['clear']<2:raise DomainError('Latest evidence has expired or clearance was reset; two fresh clearance observations are required.')
            ep['status']='closed';ep['closure']={'note':note,'at':utcnow().isoformat()}
            c.execute('UPDATE counters SET high=0,clear=0 WHERE zone_id=?',(ep['zone_id'],))
        else:raise DomainError('Unknown episode action.')
        c.execute('UPDATE episodes SET status=?,data=? WHERE id=?',(ep['status'],json.dumps(ep),episode_id));store.audit(c,'episode_'+action,{'episode_id':episode_id,'note':note})
        return ep

def queue_delivery(store,episode_id):
    with store.transaction() as c:
        row=c.execute('SELECT data FROM episodes WHERE id=?',(episode_id,)).fetchone()
        if not row:raise DomainError('Episode not found.')
        ep=json.loads(row['data'])
        if ep['status']!='acknowledged' or ep['condition_resolved']:raise DomainError('Only an acknowledged, unresolved episode can queue a notification rehearsal.')
        row=c.execute('SELECT data FROM deliveries WHERE episode_id=? AND severity=?',(episode_id,ep['severity'])).fetchone()
        if row:return json.loads(row['data'])
        record={'id':uuid4().hex,'episode_id':episode_id,'zone_id':ep['zone_id'],'severity':ep['severity'],'mode':'simulation','status':'pending','attempts':0,'created_at':utcnow().isoformat(),'message':'SIMULATION ONLY — '+ep['severity']+' research score requires review. No public warning has been issued.'}
        c.execute('INSERT INTO deliveries VALUES(?,?,?,?,?,?)',(record['id'],episode_id,ep['severity'],'pending',0,json.dumps(record)));store.audit(c,'simulation_queued',{'delivery_id':record['id'],'episode_id':episode_id});return record

def dispatch(store,fail=False):
    results=[]
    with store.transaction() as c:
        rows=c.execute("SELECT * FROM deliveries WHERE status IN ('pending','retry') ORDER BY rowid LIMIT 30").fetchall()
        for row in rows:
            d=json.loads(row['data']);ep=json.loads(c.execute('SELECT data FROM episodes WHERE id=?',(d['episode_id'],)).fetchone()['data'])
            if ep['status']!='acknowledged' or ep['condition_resolved'] or ep['severity']!=d['severity']:
                d['status']='cancelled';d['detail']='Episode changed before dispatch.'
            else:
                a=json.loads(c.execute('SELECT data FROM assessments WHERE zone_id=? ORDER BY rowid DESC LIMIT 1',(ep['zone_id'],)).fetchone()['data']);o=c.execute('SELECT data FROM observations WHERE id=?',(a['observation_id'],)).fetchone();z=c.execute('SELECT data FROM zones WHERE id=?',(ep['zone_id'],)).fetchone()
                if not quality(Observation.model_validate_json(o['data']),json.loads(z['data']))['passed']:
                    d['status']='cancelled';d['detail']='Fresh evidence is unavailable.'
                else:
                    d['attempts']+=1;d['status']='retry' if fail and d['attempts']<3 else 'failed' if fail else 'simulated_delivered';d['detail']='Injected simulation failure' if fail else 'Local rehearsal only; no external provider called.'
            d['updated_at']=utcnow().isoformat();c.execute('UPDATE deliveries SET status=?,attempts=?,data=? WHERE id=?',(d['status'],d['attempts'],json.dumps(d),d['id']));store.audit(c,'simulation_dispatch',{'delivery_id':d['id'],'status':d['status'],'attempts':d['attempts']});results.append(d)
    return results
