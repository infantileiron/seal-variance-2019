def serialize(item):
    return {c.name:getattr(item,c.name) for c in item.__table__.columns}
def serialize_many(items): return [serialize(i) for i in items]
def serialize_batch(batch,counts=None):
    data=serialize(batch)
    if counts:data.update(counts)
    return data
def serialize_manifest_item(item):return {'blind_code':item.blind_code,'group_alias':item.group_alias,'returned':item.returned_force is not None}
def serialize_mapping_item(item,process):return {'blind_code':item.blind_code,'group_alias':item.group_alias,'process_id':item.process_id,'process_code':process.code,'process_name':process.name,'returned_force':item.returned_force,'sample_id':item.sample_id}
