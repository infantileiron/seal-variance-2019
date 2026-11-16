/** @typedef {{id:number,code:string,name:string,temperature:number,dwell:number,pressure:number,note:string}} Process */
/** @typedef {{id:number,code:string,process_id:number,lot:string,force:number,flagged:boolean,note:string}} Sample */
/** @typedef {{id:number,title:string,status:'queued'|'running'|'completed'|'failed',snapshot:object,result:object|null,recommendation:string,approved:boolean}} Assessment */
/** @typedef {{id:number,code:string,title:string,lot:string,status:'open'|'sealed'|'unblinded',total:number,returned:number,missing:number,assessment_id:number|null}} BlindBatch */
/** @typedef {{blind_code:string,group_alias:string,returned:boolean}} BlindManifestItem */
export const contractsVersion='seal-variance-2';
