import json
import sqlite3
from pathlib import Path
from uuid import uuid4
from .schemas import utcnow

class Connection(sqlite3.Connection):
    def __exit__(self,*args):
        try:return super().__exit__(*args)
        finally:self.close()

class Store:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as c:
            c.executescript('''
CREATE TABLE IF NOT EXISTS zones(id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS models(id TEXT PRIMARY KEY, data TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 0);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_model ON models(active) WHERE active=1;
CREATE TABLE IF NOT EXISTS observations(id TEXT PRIMARY KEY, zone_id TEXT NOT NULL, observed_at TEXT NOT NULL, data TEXT NOT NULL, UNIQUE(zone_id,observed_at));
CREATE TABLE IF NOT EXISTS assessments(id TEXT PRIMARY KEY, observation_id TEXT UNIQUE NOT NULL, zone_id TEXT NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS episodes(id TEXT PRIMARY KEY, zone_id TEXT NOT NULL, status TEXT NOT NULL, data TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS one_open_episode ON episodes(zone_id) WHERE status!='closed';
CREATE TABLE IF NOT EXISTS counters(zone_id TEXT PRIMARY KEY, high INTEGER NOT NULL, clear INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS deliveries(id TEXT PRIMARY KEY, episode_id TEXT NOT NULL, severity TEXT NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL, data TEXT NOT NULL, UNIQUE(episode_id,severity));
CREATE TABLE IF NOT EXISTS outcomes(id TEXT PRIMARY KEY, episode_id TEXT UNIQUE NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, action TEXT NOT NULL, data TEXT NOT NULL);
''')
    def connect(self):
        c=sqlite3.connect(self.path,timeout=20,isolation_level=None,factory=Connection);c.row_factory=sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON');return c
    def transaction(self):
        # Callers use context manager; explicit BEGIN serializes workflow transitions.
        c=self.connect();c.execute('BEGIN IMMEDIATE');return c
    @staticmethod
    def audit(c,action,data):c.execute('INSERT INTO audit(created_at,action,data) VALUES(?,?,?)',(utcnow().isoformat(),action,json.dumps(data)))
    def rows(self,table):
        if table not in {'zones','episodes','deliveries','outcomes'}:raise ValueError('Unknown table')
        with self.connect() as c:return [json.loads(r['data']) for r in c.execute(f'SELECT data FROM {table} ORDER BY rowid DESC')]
    def active_model(self,c=None):
        if c is not None:
            row=c.execute('SELECT data FROM models WHERE active=1').fetchone();return json.loads(row['data']) if row else None
        with self.connect() as c:return self.active_model(c)
