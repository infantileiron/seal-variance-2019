from fastapi import APIRouter,Depends
from src.config.database import get_db
from src.utils.security import staff,editor
from src.schemas.business import ProcessInput
from src.services import processes
from src.controllers.business import serialize,serialize_many
router=APIRouter()
@router.get('/processes')
def listing(db=Depends(get_db),user=Depends(staff)):return serialize_many(processes.listing(db))
@router.post('/processes',status_code=201)
def create(data:ProcessInput,db=Depends(get_db),user=Depends(editor)):return serialize(processes.save(db,data))
@router.put('/processes/{id}')
def update(id:int,data:ProcessInput,db=Depends(get_db),user=Depends(editor)):return serialize(processes.save(db,data,id))
