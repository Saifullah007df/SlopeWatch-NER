from datetime import timedelta
import json
import pytest
from pydantic import ValidationError
from slopewatch.schemas import Observation,utcnow
from slopewatch.engine import ingest,ingest_batch,scenario_observation,snapshot,episode_action,queue_delivery,dispatch,DomainError,band,quality

@pytest.mark.parametrize('score,expected',[(0,'Low'),(.299,'Low'),(.3,'Moderate'),(.6,'High'),(.85,'Critical'),(1,'Critical')])
def test_bands(score,expected):assert band(score)==expected

def reading(mode='intense-storm',index=0):return scenario_observation('test-zone',mode,utcnow()+timedelta(seconds=index))

def test_deduplication_and_changed_payload_conflict(store):
    obs=reading();first=ingest(store,obs);second=ingest(store,obs)
    assert first['id']==second['id'] and second['duplicate']
    assert len(store.rows('episodes'))==0
    with pytest.raises(DomainError):ingest(store,obs.model_copy(update={'note':'Changed payload'}))

def test_two_reading_open_and_clearance_review(store):
    ingest(store,reading(index=1));ingest(store,reading(index=2));ep=store.rows('episodes')[0]
    assert ep['severity']=='Critical' and not ep['condition_resolved']
    with pytest.raises(DomainError):episode_action(store,ep['id'],'close','Reviewed closure')
    episode_action(store,ep['id'],'acknowledge','Inspected synthetic inputs')
    ingest(store,reading('quiet',3));assert not store.rows('episodes')[0]['condition_resolved']
    ingest(store,reading('quiet',4));assert store.rows('episodes')[0]['condition_resolved']
    closed=episode_action(store,ep['id'],'close','Two-reading clearance verified')
    assert closed['status']=='closed'
    ingest(store,reading(index=5));ingest(store,reading(index=6));assert len(store.rows('episodes'))==2

def test_unknown_resets_streak_and_never_clears(store):
    ingest(store,reading(index=1));unknown=ingest(store,reading('missing-sensor',2));assert unknown['score'] is None and unknown['band']=='Unknown'
    ingest(store,reading(index=3));assert not store.rows('episodes')
    ingest(store,reading(index=4));ep=store.rows('episodes')[0]
    episode_action(store,ep['id'],'acknowledge','Reviewed locally')
    ingest(store,reading('quiet',5));ingest(store,reading('quiet',6));assert store.rows('episodes')[0]['condition_resolved']
    ingest(store,reading('missing-sensor',7));assert not store.rows('episodes')[0]['condition_resolved']
    with pytest.raises(DomainError):episode_action(store,ep['id'],'close','Should remain open')

def test_stale_abstention_and_current_expiry(store,monkeypatch):
    old=reading().model_copy(update={'observed_at':utcnow()-timedelta(hours=2)})
    result=ingest(store,old);assert result['score'] is None
    current=reading(index=1);ingest(store,current)
    import slopewatch.engine as engine
    monkeypatch.setattr(engine,'utcnow',lambda:current.observed_at+timedelta(hours=2))
    current_view=snapshot(store)['zones'][0]['latest'];assert current_view['band']=='Unknown' and current_view['score'] is None

def test_future_and_out_of_order(store):
    ingest(store,reading(index=1))
    with pytest.raises(DomainError):ingest(store,reading().model_copy(update={'observed_at':utcnow()+timedelta(hours=1)}))
    with pytest.raises(DomainError):ingest(store,reading().model_copy(update={'observed_at':utcnow()-timedelta(minutes=1)}))

def test_batch_rolls_back_all_changes(store):
    first=reading(index=1);second=reading(index=2).model_copy(update={'zone_id':'not-present'})
    with pytest.raises(DomainError):ingest_batch(store,[first,second])
    with store.connect() as c:assert c.execute('SELECT COUNT(*) FROM observations').fetchone()[0]==0

def test_delivery_review_dedup_and_bounded_retry(store):
    ingest(store,reading(index=1));ingest(store,reading(index=2));ep=store.rows('episodes')[0]
    with pytest.raises(DomainError):queue_delivery(store,ep['id'])
    episode_action(store,ep['id'],'acknowledge','Checked evidence')
    one=queue_delivery(store,ep['id']);two=queue_delivery(store,ep['id']);assert one['id']==two['id']
    assert dispatch(store,True)[0]['status']=='retry'
    assert dispatch(store,True)[0]['attempts']==2
    assert dispatch(store,True)[0]['status']=='failed'
    assert not dispatch(store,True)

def test_delivery_is_explicitly_simulated_and_persists(store):
    ingest(store,reading(index=1));ingest(store,reading(index=2));ep=store.rows('episodes')[0];episode_action(store,ep['id'],'acknowledge','Reviewed input');queue_delivery(store,ep['id'])
    from slopewatch.store import Store
    reopened=Store(store.path);result=dispatch(reopened)[0]
    assert result['mode']=='simulation' and result['status']=='simulated_delivered'
    assert not dispatch(reopened)

def test_resolved_episode_cancels_queued_simulation(store):
    ingest(store,reading(index=1));ingest(store,reading(index=2));ep=store.rows('episodes')[0];episode_action(store,ep['id'],'acknowledge','Reviewed');queue_delivery(store,ep['id'])
    ingest(store,reading('quiet',3));ingest(store,reading('quiet',4));assert dispatch(store)[0]['status']=='cancelled'

@pytest.mark.parametrize('change',[{'soil_moisture':70},{'rain_3h_mm':700},{'rain_24h_mm':float('nan')},{'observed_at':'2026-10-17T10:00:00'},{'deformation_mm_day':-1}])
def test_measurement_contract(change):
    raw=reading().model_dump(mode='json');raw.update(change)
    with pytest.raises(ValidationError):Observation.model_validate(raw)

def test_reads_do_not_increment_streaks(store):
    ingest(store,reading());snapshot(store);snapshot(store);assert not store.rows('episodes')


def test_streaks_reset_after_evidence_gap(store):
    old_now=utcnow()-timedelta(hours=2)
    obs=scenario_observation('test-zone','intense-storm',old_now)
    ingest(store,obs,now=old_now)
    ingest(store,reading(index=1))
    assert not store.rows('episodes')

def test_stale_clearance_cannot_close(store,monkeypatch):
    ingest(store,reading(index=1));ingest(store,reading(index=2));ep=store.rows('episodes')[0]
    episode_action(store,ep['id'],'acknowledge','Reviewed')
    ingest(store,reading('quiet',3));last=reading('quiet',4);ingest(store,last)
    import slopewatch.engine as engine
    monkeypatch.setattr(engine,'utcnow',lambda:last.observed_at+timedelta(hours=2))
    with pytest.raises(DomainError):episode_action(store,ep['id'],'close','Cannot close stale clearance')

def test_boolean_and_epoch_time_are_rejected():
    raw=reading().model_dump(mode='json')
    with pytest.raises(ValidationError):Observation.model_validate(dict(raw,soil_moisture=True))
    with pytest.raises(ValidationError):Observation.model_validate(dict(raw,observed_at=12345))
