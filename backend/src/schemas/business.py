from pydantic import BaseModel,Field
class LoginInput(BaseModel):
    email:str=Field(max_length=120)
    password:str=Field(max_length=200)
class ProcessInput(BaseModel):
    code:str=Field(min_length=1,max_length=50)
    name:str=Field(min_length=2,max_length=100)
    temperature:float=Field(ge=80,le=250,allow_inf_nan=False)
    dwell:float=Field(gt=0,le=10,allow_inf_nan=False)
    pressure:float=Field(gt=0,le=2,allow_inf_nan=False)
    note:str=Field(default='',max_length=2000)
class SampleInput(BaseModel):
    code:str=Field(min_length=1,max_length=50)
    process_id:int=Field(gt=0)
    lot:str=Field(min_length=1,max_length=60)
    force:float=Field(gt=0,le=200,allow_inf_nan=False)
    flagged:bool=False
    note:str=Field(default='',max_length=1000)
class AssessmentInput(BaseModel):
    title:str=Field(min_length=2,max_length=120)
    process_ids:list[int]=Field(min_length=2,max_length=8)
    lot:str=Field(default='全部',min_length=1,max_length=60)
class RecommendationInput(BaseModel):
    selected_process_id:int=Field(gt=0)
    recommendation:str=Field(min_length=20,max_length=3000)
class BlindGroupInput(BaseModel):
    process_id:int=Field(gt=0)
    count:int=Field(ge=2,le=50)
class BlindBatchInput(BaseModel):
    title:str=Field(min_length=2,max_length=110)
    lot:str=Field(min_length=1,max_length=60)
    groups:list[BlindGroupInput]=Field(min_length=2,max_length=8)
class BlindReturnEntry(BaseModel):
    blind_code:str=Field(min_length=1,max_length=50)
    force:float=Field(gt=0,le=200,allow_inf_nan=False)
class BlindReturnInput(BaseModel):
    returns:list[BlindReturnEntry]=Field(min_length=1,max_length=500)
