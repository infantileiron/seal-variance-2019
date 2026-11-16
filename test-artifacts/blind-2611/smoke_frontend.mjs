// 前端模块图 + 页面渲染冒烟测试（无浏览器）：桩 DOM 全局，导入真实模块断言输出。
const anyEl = () => new Proxy(function () {}, { get: (t, k) => k === Symbol.toPrimitive ? () => '' : anyEl(), set: () => true, apply: () => anyEl() });
globalThis.document = { querySelector: anyEl, addEventListener: () => {}, createElement: anyEl };
globalThis.window = { addEventListener: () => {} };
globalThis.sessionStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
globalThis.location = { hash: '' };
globalThis.fetch = async () => ({ ok: false, json: async () => ({}) });

const { store } = await import('/workspace/frontend/src/stores/business.js');
const { blindPage } = await import('/workspace/frontend/src/pages/blind.js');
const { processesPage } = await import('/workspace/frontend/src/pages/processes.js');
const { samplesPage } = await import('/workspace/frontend/src/pages/samples.js');
const { analysisPage } = await import('/workspace/frontend/src/pages/analysis.js');
const { reviewsPage } = await import('/workspace/frontend/src/pages/reviews.js');
await import('/workspace/frontend/src/app.js'); // 完整模块图导入即校验

let fails = 0;
const check = (name, cond) => { console.log((cond ? 'PASS  ' : 'FAIL  ') + name); if (!cond) fails++; };

store.processes = [{ id: 1, code: 'HC-S1', name: '稳温基线', temperature: 160, dwell: .8, pressure: .32, note: '' }, { id: 2, code: 'HC-S2', name: '延时封合', temperature: 160, dwell: 1.2, pressure: .32, note: '' }];
store.samples = []; store.assessments = [];
store.batches = [{ id: 7, code: 'BB-TEST01', title: '盲测样批', lot: 'HC-1115', status: 'open', total: 4, returned: 1, missing: 3, assessment_id: null, created_by: 'a', created_at: '', sealed_at: '', unblinded_at: '' }];
store.blind = { batch: store.batches[0], items: [{ blind_code: 'BT-AAA111', group_alias: 'G1', returned: true }, { blind_code: 'BT-BBB222', group_alias: 'G2', returned: false }] };

store.user = { role: 'analyst', email: 'analyst@demo.local' };
let html = blindPage();
check('工程师盲测页：台账+建批表单', html.includes('BB-TEST01') && html.includes('blind-create-form'));
check('工程师盲测页：发放/核查/映射/封批操作', html.includes('data-manifest=7') && html.includes('data-integrity=7') && html.includes('data-mapping=7') && html.includes('data-seal=7'));
check('工程师盲测页：匿名清单不含真实工艺', html.includes('BT-AAA111') && !html.includes('process_id'));
check('原有页面可渲染', [processesPage(), samplesPage(), analysisPage(), reviewsPage()].every(h => h.length > 50));

store.user = { role: 'viewer', email: 'viewer@demo.local' };
html = blindPage();
check('只读盲测页：无建批/封批/映射入口', !html.includes('blind-create-form') && !html.includes('data-seal') && !html.includes('data-mapping') && !html.includes('data-unblind'));
check('只读盲测页：仍可核查完整性', html.includes('data-integrity=7'));

store.user = { role: 'external', email: 'external@demo.local' };
html = blindPage();
check('外协页面：仅回传通道', html.includes('外协盲测回传') && !html.includes('data-mapping') && !html.includes('data-seal') && !html.includes('blind-create-form'));
check('外协页面：回传输入框按匿名编号命名', html.includes('name="BT-BBB222"') && !html.includes('name="BT-AAA111"'));
check('外协页面：已暂存条目不再可填', html.includes('已暂存'));

store.batches[0].status = 'sealed';
html = blindPage();
check('外协页面：封批后提示截止', html.includes('回传已截止'));

store.user = { role: 'analyst', email: 'analyst@demo.local' };
store.batches[0].status = 'sealed';
html = blindPage();
check('工程师：已封批批次出现拆盲按钮', html.includes('data-unblind=7') && !html.includes('data-seal=7'));
store.batches[0].status = 'unblinded'; store.batches[0].assessment_id = 42;
html = blindPage();
check('工程师：已拆盲批次链接评议', html.includes('data-goto-assessment=42'));

console.log(fails ? `\n${fails} 项失败` : '\n前端冒烟全部通过');
process.exit(fails ? 1 : 0);
