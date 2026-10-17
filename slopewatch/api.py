import csv
import io
import json
import os
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlparse
from fastapi import FastAPI,Request,HTTPException
from fastapi.responses import Response,FileResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import Field,ValidationError
from .schemas import Strict,Zone,Observation,Note,Outcome,Scenario,Training,Batch,Dispatch,utcnow
from .store import Store
from .models import ModelError,train,summary,training_csv
from .engine import DomainError,bootstrap,ingest,ingest_batch,snapshot,scenario_observation,episode_action,queue_delivery,dispatch
ROOT=Path(__file__).resolve().parent.parent
class CSVImport(Strict):csv_text:str=Field(min_length=1,max_length=700_000)
class BodyLimit:
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']!='http' or scope['method'] not in {'POST','PUT','PATCH'}:return await self.app(scope,receive,send)
        parts=[];size=0
        while True:
            message=await receive()
            if message['type']=='http.disconnect':return
            part=message.get('body',b'');size+=len(part)
            if size>2_500_000:return await JSONResponse({'detail':'Request exceeds 2.5 MB.'},status_code=413)(scope,receive,send)
            parts.append(part)
            if not message.get('more_body'):break
        sent=False
        async def replay():
            nonlocal sent
            if not sent:sent=True;return {'type':'http.request','body':b''.join(parts),'more_body':False}
            return await receive()
        await self.app(scope,replay,send)

def observation_csv(text):
    expected=['zone_id','observed_at','source','rain_3h_mm','rain_24h_mm','rain_72h_mm','soil_moisture','deformation_mm_day','note']
    reader=csv.DictReader(io.StringIO(text))
    if reader.fieldnames!=expected:raise DomainError('Observation CSV columns must match the downloadable observation template.')
    rows=[]
    for index,row in enumerate(reader):
        if index>=300:raise DomainError('At most 300 observations per import.')
        if None in row or any(value is None for value in row.values()):raise DomainError(f'Malformed CSV row {index+2}.')
        for key in expected[3:-1]:
            if row[key]=='':row[key]=None
        try:rows.append(Observation.model_validate(row))
        except ValidationError:raise DomainError(f'Invalid units, timestamp, source or ranges in CSV row {index+2}.') from None
    if not rows:raise DomainError('CSV contains no observations.')
    return rows

def create_app(db_path=None,seed=True):
    app=FastAPI(title='SlopeWatch NER',version='1.0.0');store=Store(db_path or os.getenv('SLOPEWATCH_DB',str(ROOT/'runtime'/'workspace.sqlite3')));app.state.store=store
    if seed:bootstrap(store)
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['localhost','127.0.0.1','[::1]','testserver']);app.add_middleware(BodyLimit)
    @app.middleware('http')
    async def security(request:Request,call_next):
        if request.method in {'POST','PUT','DELETE','PATCH'}:
            origin=request.headers.get('origin')
            if (origin and (urlparse(origin).netloc!=request.headers.get('host') or urlparse(origin).scheme not in {'http','https'})) or request.headers.get('sec-fetch-site')=='cross-site':return JSONResponse({'detail':'Cross-origin changes are not allowed.'},status_code=403)
        response=await call_next(request)
        response.headers.update({'X-Content-Type-Options':'nosniff','Cache-Control':'no-store','Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"})
        return response
    @app.exception_handler(DomainError)
    async def domain_error(request,exc):return JSONResponse({'detail':str(exc)},status_code=409)
    @app.exception_handler(ModelError)
    async def model_error(request,exc):return JSONResponse({'detail':str(exc)},status_code=422)
    @app.get('/api/health')
    def health():return {'status':'ok','mode':'research-only','external_delivery':False}
    @app.get('/api/workspace')
    def workspace():return snapshot(store)
    @app.post('/api/zones',status_code=201)
    def add_zone(zone:Zone):
        with store.transaction() as c:
            if c.execute('SELECT 1 FROM zones WHERE id=?',(zone.id,)).fetchone():raise DomainError('Zone ID already exists.')
            if c.execute('SELECT COUNT(*) FROM zones').fetchone()[0]>=100:raise DomainError('This local workspace accepts at most 100 zones.')
            record=zone.model_dump();c.execute('INSERT INTO zones VALUES(?,?)',(zone.id,json.dumps(record)));store.audit(c,'zone_created',record)
        return record
    @app.post('/api/observations',status_code=201)
    def observe(observation:Observation):return ingest(store,observation)
    @app.post('/api/observations/batch',status_code=201)
    def observe_batch(batch:Batch):return ingest_batch(store,batch.observations)
    @app.post('/api/observations/import',status_code=201)
    def import_csv(payload:CSVImport):return ingest_batch(store,observation_csv(payload.csv_text))
    @app.get('/api/zones/{zone_id}/history')
    def history(zone_id:str):
        with store.connect() as c:
            if not c.execute('SELECT 1 FROM zones WHERE id=?',(zone_id,)).fetchone():raise HTTPException(404,'Zone not found.')
            rows=c.execute('SELECT data FROM assessments WHERE zone_id=? ORDER BY rowid DESC LIMIT 120',(zone_id,)).fetchall();return [json.loads(r['data']) for r in rows][::-1]
    @app.post('/api/scenarios',status_code=201)
    def scenario(payload:Scenario):return ingest(store,scenario_observation(payload.zone_id,payload.scenario))
    @app.post('/api/episodes/{episode_id}/acknowledge')
    def acknowledge(episode_id:str,payload:Note):return episode_action(store,episode_id,'acknowledge',payload.note)
    @app.post('/api/episodes/{episode_id}/close')
    def close(episode_id:str,payload:Note):return episode_action(store,episode_id,'close',payload.note)
    @app.post('/api/episodes/{episode_id}/queue')
    def queue(episode_id:str):return queue_delivery(store,episode_id)
    @app.post('/api/deliveries/dispatch')
    def deliver(payload:Dispatch):return dispatch(store,payload.simulate_failure)
    @app.post('/api/episodes/{episode_id}/outcome',status_code=201)
    def outcome(episode_id:str,payload:Outcome):
        with store.transaction() as c:
            if not c.execute('SELECT 1 FROM episodes WHERE id=?',(episode_id,)).fetchone():raise HTTPException(404,'Episode not found.')
            if c.execute('SELECT 1 FROM outcomes WHERE episode_id=?',(episode_id,)).fetchone():raise DomainError('An outcome is already recorded; retain a correction in your research curation process.')
            record=dict(payload.model_dump(),id=uuid4().hex,episode_id=episode_id,created_at=utcnow().isoformat(),training_eligible=False)
            c.execute('INSERT INTO outcomes VALUES(?,?,?)',(record['id'],episode_id,json.dumps(record)));store.audit(c,'outcome_recorded',record);return record
    @app.get('/api/outcomes')
    def outcomes():return store.rows('outcomes')
    @app.get('/api/models')
    def models():
        with store.connect() as c:return [dict(summary(json.loads(r['data'])),active=bool(r['active'])) for r in c.execute('SELECT data,active FROM models ORDER BY rowid DESC')]
    @app.post('/api/models/train',status_code=201)
    def training(payload:Training):
        with store.connect() as c:
            if c.execute('SELECT COUNT(*) FROM models').fetchone()[0]>=20:raise DomainError('Model registry limit is 20 candidates.')
        artifact=train(payload.csv_text,payload.name)
        with store.transaction() as c:
            existing=c.execute('SELECT data FROM models WHERE id=?',(artifact['id'],)).fetchone()
            if existing:return summary(json.loads(existing['data']))
            c.execute('INSERT INTO models(id,data,active) VALUES(?,?,0)',(artifact['id'],json.dumps(artifact)));store.audit(c,'candidate_trained',{'model_id':artifact['id'],'dataset_sha256':artifact['dataset_sha256'],'provenance':artifact['provenance']})
        return summary(artifact)
    @app.post('/api/models/{model_id}/activate')
    def activate(model_id:str,payload:Note):
        with store.transaction() as c:
            row=c.execute('SELECT data FROM models WHERE id=?',(model_id,)).fetchone()
            if not row:raise HTTPException(404,'Model not found.')
            c.execute('UPDATE models SET active=0 WHERE active=1');c.execute('UPDATE models SET active=1 WHERE id=?',(model_id,));c.execute('UPDATE counters SET high=0,clear=0');store.audit(c,'research_model_activated',{'model_id':model_id,'note':payload.note})
            return dict(summary(json.loads(row['data'])),active=True,notice='Applies to new observations only; historical assessments retain their original model.')
    @app.get('/api/models/{model_id}/artifact')
    def artifact(model_id:str):
        with store.connect() as c:row=c.execute('SELECT data FROM models WHERE id=?',(model_id,)).fetchone()
        if not row:raise HTTPException(404,'Model not found.')
        return Response(row['data'],media_type='application/json',headers={'Content-Disposition':f'attachment; filename="forest-{model_id}.json"'})
    @app.get('/api/audit')
    def audit():
        with store.connect() as c:return [dict(id=r['id'],created_at=r['created_at'],action=r['action'],details=json.loads(r['data'])) for r in c.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 300')]
    @app.get('/api/export/geojson')
    def geojson():
        data=snapshot(store);features=[{'type':'Feature','geometry':{'type':'Point','coordinates':[z['longitude'],z['latitude']]},'properties':{'id':z['id'],'name':z['name'],'state':z['state'],'terrain_source':z['terrain_source'],'band':z['latest']['band'] if z['latest'] else 'Unknown','score':z['latest']['score'] if z['latest'] else None,'mode':'research-only'}} for z in data['zones']]
        return Response(json.dumps({'type':'FeatureCollection','features':features}),media_type='application/geo+json',headers={'Content-Disposition':'attachment; filename="slopewatch-research-points.geojson"'})
    @app.get('/api/export/workspace')
    def export_workspace():
        data=snapshot(store);data['outcomes']=store.rows('outcomes');data['export_note']='Historical scores are model outputs, not observed probabilities.'
        return Response(json.dumps(data,indent=2),media_type='application/json',headers={'Content-Disposition':'attachment; filename="slopewatch-research-workspace.json"'})
    @app.get('/api/templates/{name}')
    def templates(name:str):
        if name=='training':content=training_csv(rows=400);filename='synthetic-training-example.csv'
        elif name=='observations':
            buffer=io.StringIO();writer=csv.writer(buffer);writer.writerow(['zone_id','observed_at','source','rain_3h_mm','rain_24h_mm','rain_72h_mm','soil_moisture','deformation_mm_day','note']);writer.writerow(['gangtok',utcnow().isoformat(),'manual-unverified',5,25,70,.35,.5,'Example values only']);content=buffer.getvalue();filename='observation-template.csv'
        else:raise HTTPException(404,'Template not found.')
        return Response(content,media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="{filename}"'})
    @app.get('/api/reference')
    def reference():return {'design':(ROOT/'docs/system-design.md').read_text(),'research':(ROOT/'docs/existing-systems.md').read_text(),'contract':(ROOT/'docs/data-contract.md').read_text()}
    @app.get('/')
    def home():return FileResponse(ROOT/'web/index.html')
    app.mount('/assets',StaticFiles(directory=ROOT/'web'),name='assets');return app
