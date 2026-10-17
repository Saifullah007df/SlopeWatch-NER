import pytest
from slopewatch.models import train,training_csv
from slopewatch.store import Store
from slopewatch.schemas import Zone
import json
@pytest.fixture(scope='session')
def model():return train(training_csv(rows=800),'Test synthetic baseline','synthetic')
@pytest.fixture
def store(tmp_path,model):
    store=Store(tmp_path/'workspace.sqlite3')
    z=Zone(id='test-zone',name='Test slope',state='Sikkim',latitude=27.3,longitude=88.6,slope_deg=38,elevation_m=1600,terrain_source='synthetic-fixture')
    with store.transaction() as c:
        c.execute('INSERT INTO models(id,data,active) VALUES(?,?,1)',(model['id'],json.dumps(model)))
        c.execute('INSERT INTO zones VALUES(?,?)',(z.id,z.model_dump_json()))
    return store
