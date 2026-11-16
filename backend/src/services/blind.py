import secrets
from datetime import datetime,timezone
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
import redis
from src.models.entities import BlindBatch,BlindItem,Process,Sample,Assessment
from src.services.assessments import queue

def now():return datetime.now(timezone.utc).isoformat()
def get(db,id):
    batch=db.get(BlindBatch,id)
    if not batch:raise HTTPException(404,'盲测批不存在')
    return batch
def items_of(db,id):return db.scalars(select(BlindItem).where(BlindItem.batch_id==id).order_by(BlindItem.id)).all()
def counts(db,batch):
    items=items_of(db,batch.id);returned=sum(i.returned_force is not None for i in items)
    return {'total':len(items),'returned':returned,'missing':len(items)-returned}
def listing(db):
    batches=db.scalars(select(BlindBatch).order_by(BlindBatch.id.desc())).all()
    return [(b,counts(db,b)) for b in batches]
def new_code(db,model,prefix):
    for _ in range(30):
        code=prefix+secrets.token_hex(3).upper()
        if not db.scalar(select(model).where(model.code==code if model is BlindBatch else model.blind_code==code)):return code
    raise HTTPException(503,'匿名编号分配冲突，请重试')
def create(db,data,user):
    ids=[g.process_id for g in data.groups]
    if len(ids)!=len(set(ids)):raise HTTPException(422,'同一工艺在盲测批中只能出现一次')
    processes={}
    for pid in ids:
        process=db.get(Process,pid)
        if not process:raise HTTPException(404,'工艺方案不存在')
        processes[pid]=process
    batch=BlindBatch(code=new_code(db,BlindBatch,'BB-'),title=data.title,lot=data.lot,status='open',created_by=user.email,created_at=now())
    db.add(batch);db.flush()
    shuffled=ids[:];secrets.SystemRandom().shuffle(shuffled)
    alias={pid:f'G{i+1}' for i,pid in enumerate(shuffled)}
    for g in data.groups:
        for _ in range(g.count):db.add(BlindItem(batch_id=batch.id,blind_code=new_code(db,BlindItem,'BT-'),group_alias=alias[g.process_id],process_id=g.process_id))
    db.commit();db.refresh(batch);return batch
def manifest(db,id):
    batch=get(db,id)
    items=db.scalars(select(BlindItem).where(BlindItem.batch_id==id).order_by(BlindItem.blind_code)).all()
    return batch,items
def mapping(db,id):
    batch=get(db,id)
    items=db.scalars(select(BlindItem).where(BlindItem.batch_id==id).order_by(BlindItem.group_alias,BlindItem.blind_code)).all()
    processes={p.id:p for p in db.scalars(select(Process)).all()}
    return batch,items,processes
def integrity(db,id):
    batch=get(db,id);items=items_of(db,id)
    missing=[i.blind_code for i in items if i.returned_force is None]
    return {'batch_id':id,'status':batch.status,'total':len(items),'returned':len(items)-len(missing),'missing':missing,'complete':not missing}
def stage_returns(db,id,data,user):
    batch=db.scalar(select(BlindBatch).where(BlindBatch.id==id).with_for_update())
    if not batch:raise HTTPException(404,'盲测批不存在')
    if batch.status!='open':raise HTTPException(409,'盲测批已封批，迟到回传不再接收，已生成结果不受影响')
    codes=[r.blind_code for r in data.returns]
    if len(codes)!=len(set(codes)):raise HTTPException(422,'同一回传包含重复试条编号，整批拒绝')
    incoming={r.blind_code:r.force for r in data.returns}
    items={i.blind_code:i for i in items_of(db,id)}
    wrong=[c for c in codes if c not in items]
    if wrong:raise HTTPException(422,'存在错号试条，整批拒绝：'+'、'.join(wrong))
    conflicts=[c for c in codes if items[c].returned_force is not None and items[c].returned_force!=incoming[c]]
    if conflicts:raise HTTPException(409,'试条已回传且数值不一致，暂存值不可改写：'+'、'.join(conflicts))
    ts=now()
    for r in data.returns:
        item=items[r.blind_code]
        if item.returned_force is not None:continue
        item.returned_force=r.force;item.returned_at=ts;item.returned_by=user.email
    db.commit();return integrity(db,id)
def seal(db,id,user):
    batch=db.scalar(select(BlindBatch).where(BlindBatch.id==id).with_for_update())
    if not batch:raise HTTPException(404,'盲测批不存在')
    if batch.status!='open':raise HTTPException(409,'盲测批已封批或已拆盲，封批只能执行一次')
    batch.status='sealed';batch.sealed_at=now();db.commit();db.refresh(batch);return batch
def unblind(db,id,user):
    batch=db.scalar(select(BlindBatch).where(BlindBatch.id==id).with_for_update())
    if not batch:raise HTTPException(404,'盲测批不存在')
    if batch.status=='unblinded':raise HTTPException(409,'盲测批已拆盲，样本与评议已生成，重复拆盲不会重建')
    if batch.status!='sealed':raise HTTPException(409,'请先封批固定回传边界，再拆盲')
    items=items_of(db,id)
    missing=[i.blind_code for i in items if i.returned_force is None]
    if missing:raise HTTPException(422,f'存在{len(missing)}条缺测试条（{"、".join(missing[:8])}{"…" if len(missing)>8 else ""}），缺测不给结论')
    processes={p.id:p for p in db.scalars(select(Process)).all()}
    ts=now()
    try:
        groups={}
        for item in items:
            sample=Sample(code=item.blind_code,process_id=item.process_id,lot=batch.lot,force=item.returned_force,flagged=False,note=f'盲测批{batch.code}拆盲转入')
            db.add(sample);db.flush();item.sample_id=sample.id
            groups.setdefault(item.process_id,[]).append({'code':item.blind_code,'force':item.returned_force,'flagged':False,'lot':batch.lot})
        glist=[{'id':pid,'code':processes[pid].code,'name':processes[pid].name,'temperature':processes[pid].temperature,'dwell':processes[pid].dwell,'pressure':processes[pid].pressure,'samples':groups[pid]} for pid in sorted(groups)]
        assessment=Assessment(title=f'盲测{batch.code} · {batch.title}'[:120],lot=batch.lot,status='queued',snapshot={'lot':batch.lot,'groups':glist},created_at=ts)
        db.add(assessment);db.flush()
        batch.assessment_id=assessment.id;batch.status='unblinded';batch.unblinded_at=ts
        db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'试条转入失败，本批已全部回滚，未生成样本或评议；请排除编号冲突后重试')
    db.refresh(batch)
    try:queue.lpush('seal:assessments',batch.assessment_id)
    except redis.RedisError:
        assessment=db.get(Assessment,batch.assessment_id);assessment.status='failed';assessment.error='队列不可用，请恢复后新建评议';db.commit()
    return batch
