from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FEATURES=['rain_3h_mm','rain_24h_mm','rain_72h_mm','soil_moisture','slope_deg','elevation_m','deformation_mm_day']
BOUNDS={'rain_3h_mm':(0,1000),'rain_24h_mm':(0,2000),'rain_72h_mm':(0,4000),'soil_moisture':(0,1),'slope_deg':(0,85),'elevation_m':(0,9000),'deformation_mm_day':(0,100)}
def utcnow():return datetime.now(timezone.utc)

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
class Zone(Strict):
    id:str=Field(pattern=r'^[a-z0-9-]{2,40}$')
    name:str=Field(min_length=2,max_length=100)
    state:str=Field(min_length=2,max_length=60)
    latitude:float=Field(ge=21,le=30)
    longitude:float=Field(ge=87,le=98)
    slope_deg:float=Field(ge=0,le=85)
    elevation_m:float=Field(ge=0,le=9000)
    terrain_source:Literal['synthetic-fixture','user-supplied-unverified']='user-supplied-unverified'
class Observation(Strict):
    zone_id:str=Field(min_length=2,max_length=40)
    observed_at:datetime
    source:Literal['synthetic','manual-unverified','sensor-import-unverified']
    rain_3h_mm:float|None=Field(default=None,ge=0,le=1000)
    rain_24h_mm:float|None=Field(default=None,ge=0,le=2000)
    rain_72h_mm:float|None=Field(default=None,ge=0,le=4000)
    soil_moisture:float|None=Field(default=None,ge=0,le=1)
    deformation_mm_day:float|None=Field(default=None,ge=0,le=100)
    note:str=Field(default='',max_length=400)
    @field_validator('rain_3h_mm','rain_24h_mm','rain_72h_mm','soil_moisture','deformation_mm_day',mode='before')
    @classmethod
    def no_boolean_values(cls,value):
        if isinstance(value,bool):raise ValueError('Measurements cannot be Boolean values.')
        return value
    @field_validator('observed_at',mode='before')
    @classmethod
    def timestamp_type(cls,value):
        if not isinstance(value,(str,datetime)):raise ValueError('Use an ISO timestamp with an explicit timezone.')
        return value
    @field_validator('observed_at')
    @classmethod
    def aware(cls,value):
        if value.tzinfo is None:raise ValueError('Timestamp must include a timezone offset or Z.')
        return value.astimezone(timezone.utc)
    @model_validator(mode='after')
    def rainfall_order(self):
        for a,b in [(self.rain_3h_mm,self.rain_24h_mm),(self.rain_24h_mm,self.rain_72h_mm),(self.rain_3h_mm,self.rain_72h_mm)]:
            if a is not None and b is not None and a>b:raise ValueError('Accumulated rain must satisfy 3h <= 24h <= 72h.')
        return self
class Note(Strict):
    note:str=Field(min_length=3,max_length=600)
    @field_validator('note')
    @classmethod
    def nonblank(cls,value):
        if len(value.strip())<3:raise ValueError('Provide a meaningful note.')
        return value.strip()
class Outcome(Note):
    outcome:Literal['landslide','no-landslide','uncertain']
class Scenario(Strict):
    zone_id:str
    scenario:Literal['quiet','rainfall-rise','intense-storm','missing-sensor','stale-reading']
class Training(Strict):
    csv_text:str=Field(min_length=1,max_length=2_000_000)
    name:str=Field(min_length=3,max_length=80)
class Batch(Strict):
    observations:list[Observation]=Field(min_length=1,max_length=300)
class Dispatch(Strict):
    simulate_failure:bool=False
