#!/usr/bin/env python3
"""盲测批端到端验证：匿名隔离、越权查映射、回传暂存、封批争抢、同一封批边界、
半途失败回滚、重试幂等、迟到回传、拆盲归组与 ANOVA。运行前需后端+worker+PG+Redis 就绪。"""
import json, os, sys, time, threading, urllib.request, urllib.error

BASE = os.environ.get('BASE_URL', 'http://127.0.0.1:19204')
DB_URL = os.environ.get('DATABASE_URL', 'postgresql+psycopg://seal:seal_local_pass@127.0.0.1:15432/seal')
PASSWD = 'Demo123!'
failures = []

def call(method, path, token=None, body=None):
    req = urllib.request.Request(BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type': 'application/json', **({'Authorization': 'Bearer ' + token} if token else {})})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as e:
        raw = e.read()
        try: data = json.loads(raw or b'{}')
        except Exception: data = {'raw': raw.decode(errors='replace')}
        return e.code, data

def check(name, cond, extra=''):
    print(('PASS  ' if cond else 'FAIL  ') + name + (('  | ' + str(extra)) if extra else ''))
    if not cond: failures.append(name)

def login(role):
    s, d = call('POST', '/auth/login', body={'email': role + '@demo.local', 'password': PASSWD})
    assert s == 200, (role, s, d)
    return d['access_token']

def make_batch(token, title, groups):
    s, d = call('POST', '/blind-batches', token, {'title': title, 'lot': 'HC-1115', 'groups': groups})
    assert s == 201, (s, d)
    return d

def manifest(token, bid):
    s, d = call('GET', f'/blind-batches/{bid}', token)
    assert s == 200, (s, d)
    return d

def ret(token, bid, pairs):
    return call('POST', f'/blind-batches/{bid}/returns', token, {'returns': [{'blind_code': c, 'force': f} for c, f in pairs]})

admin, analyst, viewer, external = login('admin'), login('analyst'), login('viewer'), login('external')
print('== 四个角色登录成功 ==')

# ---------- 0. 原有样本入口保留 ----------
s, d = call('POST', '/samples', analyst, {'code': 'HC-S1-900', 'process_id': 1, 'lot': 'HC-1115', 'force': 23.5, 'flagged': False, 'note': '原有入口回归'})
check('原有样本入口仍可录入', s == 201, d.get('code'))
s, d = call('GET', '/samples', analyst)
check('原有样本台账可查询', s == 200 and any(x['code'] == 'HC-S1-900' for x in d))

# ---------- 1. 建立盲测批：匿名编号 ----------
s, d = call('GET', '/processes', analyst)
pids = [p['id'] for p in d]
batchA = make_batch(analyst, '验证批A 三工艺盲测', [{'process_id': p, 'count': 4} for p in pids[:3]])
A = batchA['id']
check('建立盲测批并生成匿名批号', batchA['code'].startswith('BB-') and batchA['status'] == 'open', batchA['code'])
detA = manifest(analyst, A)
codesA = [i['blind_code'] for i in detA['items']]
check('12条试条全部匿名编号(BT-)', len(codesA) == 12 and all(c.startswith('BT-') for c in codesA))
check('匿名编号全局唯一', len(set(codesA)) == 12)
check('匿名清单不含真实工艺字段', all(set(i.keys()) == {'blind_code', 'group_alias', 'returned'} for i in detA['items']))
check('匿名批详情不泄露 process_id', 'process_id' not in json.dumps(detA))

# ---------- 2. 外协隔离与越权查映射 ----------
for path in ['/samples', '/processes', '/assessments']:
    s, _ = call('GET', path, external)
    check(f'外协禁入原有模块 {path}', s == 403)
s, d = call('GET', '/blind-batches', external)
check('外协可收取盲测批列表', s == 200)
s, d = call('GET', f'/blind-batches/{A}', external)
check('外协仅见匿名清单', s == 200 and all('process_id' not in i and 'process_code' not in i for i in d['items']))
s, d = call('GET', f'/blind-batches/{A}/mapping', external)
check('越权查映射：外协 403', s == 403, d.get('detail'))
s, d = call('GET', f'/blind-batches/{A}/mapping', viewer)
check('越权查映射：只读 403', s == 403)
s, d = call('GET', f'/blind-batches/{A}/mapping', analyst)
check('内部工艺账号可查映射', s == 200 and len(d['items']) == 12 and all('process_code' in i for i in d['items']))
s, d = call('GET', f'/blind-batches/{A}/integrity', external)
check('外协不可核查完整性', s == 403)
s, d = call('POST', f'/blind-batches/{A}/seal', external)
check('外协不可封批', s == 403)
s, d = call('POST', '/blind-batches', external, {'title': 'x', 'lot': 'y', 'groups': [{'process_id': 1, 'count': 2}, {'process_id': 2, 'count': 2}]})
check('外协不可建批', s == 403)
s, d = call('POST', f'/blind-batches/{A}/unblind', viewer)
check('只读不可拆盲', s == 403)
s, d = call('POST', f'/blind-batches/{A}/returns', viewer, {'returns': [{'blind_code': codesA[0], 'force': 20.0}]})
check('只读不可回传', s == 403)

# ---------- 3. 回传暂存：错号 / 重复 / 幂等 / 冲突 ----------
batchB = make_batch(analyst, '验证批B 数据质量', [{'process_id': pids[0], 'count': 2}, {'process_id': pids[1], 'count': 2}])
B = batchB['id']
codesB = [i['blind_code'] for i in manifest(analyst, B)['items']]
s, d = ret(external, B, [('BT-WRONG1', 20.0)])
check('错号整批拒绝(422)', s == 422, d.get('detail'))
s, d = ret(external, B, [(codesA[0], 20.0)])
check('他批编号在本批视同错号', s == 422)
s, d = call('GET', f'/blind-batches/{B}/integrity', analyst)
check('错号回传不留痕(暂存0条)', s == 200 and d['returned'] == 0)
s, d = ret(external, B, [(codesB[0], 21.0), (codesB[0], 21.0)])
check('同一回传内重复试条整批拒绝', s == 422)
s, d = ret(external, B, [(codesB[0], 21.5), (codesB[1], 22.5)])
check('有效回传暂存', s == 200 and d['returned'] == 2, d)
s, d = ret(external, B, [(codesB[0], 21.5)])
check('同值重传幂等(重试安全)', s == 200 and d['returned'] == 2)
s, d = ret(external, B, [(codesB[0], 99.9)])
check('异值改写被拒(409)', s == 409)
s, d = call('GET', f'/blind-batches/{B}/integrity', analyst)
check('完整性核查：缺测2条', s == 200 and d['returned'] == 2 and sorted(d['missing']) == sorted(codesB[2:]), d)

# ---------- 4. 缺测不给结论 ----------
s, d = call('POST', f'/blind-batches/{B}/seal', analyst)
check('批B封批', s == 200)
s, d = call('POST', f'/blind-batches/{B}/unblind', analyst)
check('缺测批拆盲被拒，不给结论', s == 422, d.get('detail'))
s, d = call('GET', f'/blind-batches/{B}', analyst)
check('缺测批保持已封批、无评议生成', d['batch']['status'] == 'sealed' and d['batch']['assessment_id'] is None)

# ---------- 5. 批A 回传齐 + 封批争抢 ----------
forcesA = {c: round(20 + i * 0.37, 2) for i, c in enumerate(codesA)}
s, d = ret(external, A, list(forcesA.items()))
check('批A全部回传暂存', s == 200 and d['returned'] == 12 and d['complete'])
seal_results = []
barrier = threading.Barrier(2)
def seal_race():
    barrier.wait()
    seal_results.append(call('POST', f'/blind-batches/{A}/seal', analyst)[0])
t1, t2 = threading.Thread(target=seal_race), threading.Thread(target=seal_race)
t1.start(); t2.start(); t1.join(); t2.join()
check('封批争抢：恰好一次成功一次409', sorted(seal_results) == [200, 409], seal_results)

# ---------- 6. 同一封批边界：最后一笔回传 vs 封批 并发 ----------
rounds = []
for r in range(5):
    bt = make_batch(analyst, f'验证批C{r} 边界并发', [{'process_id': pids[0], 'count': 2}, {'process_id': pids[1], 'count': 2}])
    cs = [i['blind_code'] for i in manifest(analyst, bt['id'])['items']]
    s, d = ret(external, bt['id'], [(c, 20.0 + r) for c in cs[:-1]])
    assert s == 200 and d['returned'] == 3
    bar = threading.Barrier(2); out = {}
    def do_ret(): bar.wait(); out['ret'] = ret(external, bt['id'], [(cs[-1], 25.0)])[0]
    def do_seal(): bar.wait(); out['seal'] = call('POST', f"/blind-batches/{bt['id']}/seal", analyst)[0]
    x, y = threading.Thread(target=do_ret), threading.Thread(target=do_seal)
    x.start(); y.start(); x.join(); y.join()
    s, integ = call('GET', f"/blind-batches/{bt['id']}/integrity", analyst)
    ok = (out['ret'] == 200 and out['seal'] == 200 and integ['complete']) or (out['ret'] == 409 and out['seal'] == 200 and integ['returned'] == 3)
    rounds.append((out, integ['returned'], integ['complete']))
    check(f'边界并发轮次{r+1}：回传与封批同一边界，无撕裂', ok, out)

# ---------- 7. 半途失败：任一试条转入失败全部回滚 ----------
s, before = call('GET', '/samples', analyst)
n_before = len(before)
s, d = call('POST', '/samples', analyst, {'code': codesA[5], 'process_id': pids[0], 'lot': 'HC-1115', 'force': 19.9, 'flagged': False, 'note': '人为制造编号冲突'})
check('预置与盲码冲突的样本编号', s == 201)
s, d = call('POST', f'/blind-batches/{A}/unblind', analyst)
check('半途失败：转入冲突整批回滚(409)', s == 409, d.get('detail'))
s, d = call('GET', f'/blind-batches/{A}', analyst)
check('回滚后仍为已封批、未生成评议', d['batch']['status'] == 'sealed' and d['batch']['assessment_id'] is None)
s, after = call('GET', '/samples', analyst)
leaked = [x for x in after if x['code'] in codesA and x['code'] != codesA[5]]
check('回滚后无任何试条样本残留', len(after) == n_before + 1 and not leaked)
s, d = call('GET', '/assessments', analyst)
check('回滚后未建评议', not any(a['title'].startswith('盲测' + batchA['code']) for a in d))

# ---------- 8. 排除冲突后重试：不重复入样、不重复建评议 ----------
import psycopg
with psycopg.connect(DB_URL.replace('postgresql+psycopg://', 'postgresql://')) as conn:
    conn.execute(f"DELETE FROM samples WHERE code = %s", (codesA[5],))
    conn.commit()
s, d = call('POST', f'/blind-batches/{A}/unblind', analyst)
check('排除冲突后重试拆盲成功', s == 200 and d['status'] == 'unblinded' and d['assessment_id'], d.get('code'))
aid = d['assessment_id']
s, d = call('POST', f'/blind-batches/{A}/unblind', analyst)
check('重复拆盲被拒(409)，不重复入样建评议', s == 409)
s, after2 = call('GET', '/samples', analyst)
blind_samples = [x for x in after2 if x['code'] in codesA]
check('入库试条样本恰为12条', len(blind_samples) == 12)
s, d = call('GET', '/assessments', analyst)
check('本批评议唯一', sum(1 for a in d if a['title'].startswith('盲测' + batchA['code'])) == 1)

# ---------- 9. 拆盲后迟到回传不改结果 ----------
s, d = ret(external, A, [(codesA[0], 11.11)])
check('拆盲后迟到回传409', s == 409, d.get('detail'))
s, d = call('GET', f'/assessments/{aid}', analyst)
for _ in range(30):
    if d['status'] in ('completed', 'failed'): break
    time.sleep(1); s, d = call('GET', f'/assessments/{aid}', analyst)
check('拆盲评议后台计算完成', d['status'] == 'completed', d.get('error'))
result = d['result']
s, d2 = call('GET', f'/assessments/{aid}', analyst)
check('迟到回传后评议结果不变', d2['result'] == result)

# ---------- 10. 归组入库与 ANOVA 正确性 ----------
s, mapping = call('GET', f'/blind-batches/{A}/mapping', analyst)
mmap = {i['blind_code']: i for i in mapping['items']}
s, allsamples = call('GET', '/samples', analyst)
by_code = {x['code']: x for x in allsamples}
ok = all(by_code[c]['process_id'] == mmap[c]['process_id'] and abs(by_code[c]['force'] - mmap[c]['returned_force']) < 1e-9 and by_code[c]['lot'] == 'HC-1115' for c in codesA)
check('12条样本按真实工艺归组入库且数值一致', ok)
check('评议组别与真实工艺一一对应', sorted(g['id'] for g in result['groups']) == sorted(set(pids[:3])))
check('每组 n=4 且均值与回传一致', all(g['n'] == 4 for g in result['groups']) and all(
    abs(g['mean'] - sum(forcesA[c] for c in codesA if mmap[c]['process_id'] == g['id']) / 4) < 1e-9 for g in result['groups']))
check('ANOVA 含 F/p/η²/校验和', all(k in result for k in ('f', 'p', 'eta_squared', 'checksum', 'ss_within')))
s, d = call('GET', f'/blind-batches/{A}', external)
check('拆盲后外协清单仍无映射泄露', all('process_id' not in i for i in d['items']))

print()
if failures:
    print(f'共 {len(failures)} 项失败：'); [print(' -', f) for f in failures]; sys.exit(1)
print('全部验证通过。')
