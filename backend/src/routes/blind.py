from fastapi import APIRouter,Depends
from src.config.database import get_db
from src.utils.security import current_user,editor,staff,mapping_reader,returner
from src.schemas.business import BlindBatchInput,BlindReturnInput
from src.services import blind
from src.controllers.business import serialize,serialize_batch,serialize_manifest_item,serialize_mapping_item
router=APIRouter()
@router.get('/blind-batches')
def listing(db=Depends(get_db),user=Depends(current_user)):return [serialize_batch(b,c) for b,c in blind.listing(db)]
@router.post('/blind-batches',status_code=201)
def create(data:BlindBatchInput,db=Depends(get_db),user=Depends(editor)):
    batch=blind.create(db,data,user);return serialize_batch(batch,blind.counts(db,batch))
@router.get('/blind-batches/{id}')
def detail(id:int,db=Depends(get_db),user=Depends(current_user)):
    batch,items=blind.manifest(db,id)
    return {'batch':serialize_batch(batch,blind.counts(db,batch)),'items':[serialize_manifest_item(i) for i in items]}
@router.get('/blind-batches/{id}/mapping')
def mapping(id:int,db=Depends(get_db),user=Depends(mapping_reader)):
    batch,items,processes=blind.mapping(db,id)
    return {'batch':serialize_batch(batch,blind.counts(db,batch)),'items':[serialize_mapping_item(i,processes[i.process_id]) for i in items]}
@router.get('/blind-batches/{id}/integrity')
def integrity(id:int,db=Depends(get_db),user=Depends(staff)):return blind.integrity(db,id)
@router.post('/blind-batches/{id}/returns')
def returns(id:int,data:BlindReturnInput,db=Depends(get_db),user=Depends(returner)):return blind.stage_returns(db,id,data,user)
@router.post('/blind-batches/{id}/seal')
def seal(id:int,db=Depends(get_db),user=Depends(editor)):return serialize(blind.seal(db,id,user))
@router.post('/blind-batches/{id}/unblind')
def unblind(id:int,db=Depends(get_db),user=Depends(editor)):return serialize(blind.unblind(db,id,user))
