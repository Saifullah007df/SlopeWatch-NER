import json
from fastapi.testclient import TestClient
import pytest
from slopewatch.api import create_app
from slopewatch.models import training_csv
from slopewatch.engine import scenario_observation
from slopewatch.schemas import utcnow
from datetime import timedelta

@pytest.fixture
def client(store):
    with TestClient(create_app(store.path,seed=False)) as c:yield c

def post_obs(client,mode,index):
    reading=scenario_observation('test-zone',mode,utcnow()+timedelta(seconds=index))
    return client.post('/api/observations',json=reading.model_dump(mode='json'))

def test_full_episode_journey(client):
    assert client.get('/').status_code==200
    assert client.get('/assets/app.js').status_code==200
    assert client.get('/api/health').json()['external_delivery'] is False
    post_obs(client,'intense-storm',1);post_obs(client,'intense-storm',2)
    ep=client.get('/api/workspace').json()['episodes'][0]
    assert client.post(f'/api/episodes/{ep["id"]}/acknowledge',json={'note':'Reviewed test evidence'}).status_code==200
    assert client.post(f'/api/episodes/{ep["id"]}/queue').status_code==200
    result=client.post('/api/deliveries/dispatch',json={}).json()
    assert result[0]['status']=='simulated_delivered'
    post_obs(client,'quiet',3);post_obs(client,'quiet',4)
    assert client.post(f'/api/episodes/{ep["id"]}/close',json={'note':'Clearance checked'}).status_code==200
    outcome={'note':'No independently verified outcome','outcome':'uncertain'}
    saved=client.post(f'/api/episodes/{ep["id"]}/outcome',json=outcome)
    assert saved.status_code==201 and saved.json()['training_eligible'] is False
    assert client.post(f'/api/episodes/{ep["id"]}/outcome',json=outcome).status_code==409
    assert len(client.get('/api/audit').json())>4

def test_import_atomicity_and_unknown(client):
    example=client.get('/api/templates/observations').text.replace('gangtok','test-zone')
    assert client.post('/api/observations/import',json={'csv_text':example}).status_code==201
    with_missing=client.post('/api/observations',json={'zone_id':'test-zone','observed_at':(utcnow()+timedelta(seconds=1)).isoformat(),'source':'sensor-import-unverified'})
    assert with_missing.status_code==201 and with_missing.json()['band']=='Unknown'
    bad=client.post('/api/observations/import',json={'csv_text':'bad,columns\n1,2'})
    assert bad.status_code==409

def test_candidate_not_auto_activated_and_history_keeps_lineage(client):
    original=client.get('/api/models').json()[0]['id']
    before=post_obs(client,'quiet',1).json()
    candidate=client.post('/api/models/train',json={'name':'Candidate research model','csv_text':training_csv(seed=12,rows=240)})
    assert candidate.status_code==201
    cid=candidate.json()['id'];assert cid!=original
    assert next(m for m in client.get('/api/models').json() if m['id']==original)['active']
    assert client.post(f'/api/models/{cid}/activate',json={'note':'Explicit research review'}).status_code==200
    after=post_obs(client,'quiet',2).json();assert after['model_id']==cid
    history=client.get('/api/zones/test-zone/history').json();assert history[0]['model_id']==original
    artifact=client.get(f'/api/models/{cid}/artifact').json();assert artifact['schema']=='forest-v1'

def test_headers_bounds_and_same_origin(client):
    assert client.get('/api/health',headers={'Host':'evil.example'}).status_code==400
    assert client.post('/api/scenarios',headers={'Origin':'https://evil.example'},json={'zone_id':'test-zone','scenario':'quiet'}).status_code==403
    assert client.post('/api/models/train',content='x'*2_500_001,headers={'Content-Type':'application/json'}).status_code==413
    assert client.get('/').headers['content-security-policy'].startswith("default-src 'self'")
    assert client.post('/api/zones',json={'id':'test','name':'Test','state':'State','latitude':27,'longitude':89,'slope_deg':100,'elevation_m':1000}).status_code==422

def test_zone_and_exports(client):
    z={'id':'new-zone','name':'Research station','state':'Sikkim','latitude':27,'longitude':89,'slope_deg':30,'elevation_m':1200}
    assert client.post('/api/zones',json=z).status_code==201
    assert client.post('/api/zones',json=z).status_code==409
    assert client.get('/api/zones/unknown/history').status_code==404
    geo=client.get('/api/export/geojson');assert geo.json()['type']=='FeatureCollection'
    assert geo.json()['features'][0]['geometry']['coordinates']==[89,27]
    assert client.get('/api/export/workspace').json()['mode']=='research-only'
    assert client.get('/api/reference').status_code==200

def test_bootstrap_is_idempotent(tmp_path):
    path=tmp_path/'seed.sqlite3'
    with TestClient(create_app(path)) as c:
        one=c.get('/api/workspace').json();assert len(one['zones'])==8
        assert sum(z['latest']['band']=='Unknown' for z in one['zones'])==2
    with TestClient(create_app(path)) as c:
        two=c.get('/api/workspace').json();assert len(two['episodes'])==len(one['episodes'])
