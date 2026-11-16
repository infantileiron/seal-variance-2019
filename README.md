# 和川包装 · 包装工艺方差评估

面向封合工艺工程师的小型业务应用：登记工艺参数与拉力测量，提交单因素 ANOVA，结合工程条件起草推荐，由负责人签核冻结并导出完整评议。

## 真实场景

模拟客户为和川包装工艺研究室：6 位工艺工程师、1 位负责人，比较同批 BOPP/PE 复合膜的三种封口参数。原先由实验员把试条拉力抄入工作簿，工程师手算平均数后在聊天里确认参数，负责人另存结论。三个痛点是异常样本是否剔除说不清、工艺参数与历史结论脱节、只看平均值而忽略组内变异。

上游是封口机参数单与独立试条测量记录；本应用替代人工统计、证据归档与结论确认；下游为负责人批准下一轮试产验证。应用不把统计显著性直接当作工艺合格判定。

## 业务模块

1. **方案库**：维护方案编号、封口温度、保压时间、压力、材料说明；支持修订。
2. **拉力录入**：按方案与材料批次登记最大拉力，支持筛选、异常标记与修订；标记样本保留在统计中。
3. **方差分析**：选择至少两个方案与材料批次，后台 worker 计算 SS、F、p、η²；每次提交冻结参数和测量快照。
4. **工艺评议**：查看组别均值/标准差，填写推荐方案和至少20字业务理由，负责人签核后冻结，下载 JSON，负责人可查看操作审计。
5. **外协盲测批**：把工艺与试条替换为匿名编号后发放外协测拉力，避免取样受工艺参数影响。回传先暂存，封批固定边界后拆盲：暂存拉力按真实工艺归组入库并自动生成 ANOVA 评议。

### 盲测批流程与口径

- **建批**：工程师选择 2–8 个工艺、每组 2–50 条试条；系统为每批生成匿名批号（`BB-`）、每条试条生成全局唯一盲码（`BT-`），每个工艺分配随机匿名组号（G1、G2…，顺序与建批顺序无关）。
- **发放**：匿名清单仅含盲码与匿名组号，可下载 JSON 交付外协；任何列表/详情接口都不返回真实映射。
- **回传**：外协（或内部代录）按盲码回传拉力，先暂存。错号与他批编号整批拒绝（422）；同一回传内重复编号整批拒绝；同值重传幂等（重试安全）；异值改写拒绝（409）。暂存值不可改写。
- **核查完整性**：随时可查已回传/缺测清单。缺测、错号或重复试条不给结论。
- **封批**：open→sealed，行锁保证只成功一次（并发争抢得 409）。封批即回传边界：回传与封批/拆盲并发时，以封批为同一边界，迟到回传 409。
- **拆盲**：sealed→unblinded 单事务完成——逐条把暂存拉力转为正式样本（样本编号即盲码，可溯源）、按真实工艺归组、创建评议并提交后台 ANOVA。任一试条转入失败（如编号冲突）整批回滚，不留样本或评议；排除冲突后重试安全，重复拆盲 409 不重复入样或建评议。拆盲后迟到回传不影响已生成结果。
- **权限**：映射（盲码↔真实工艺）仅 admin/analyst 可查；外协角色（external）只能收取匿名清单与回传拉力，原有四个模块接口对其全部关闭；viewer 可看批次与完整性，不能看映射、不能回传/封批/拆盲。

### 角色与账号

| 角色 | 账号 | 权限与典型动作 |
|---|---|---|
| admin / 工艺负责人 | admin@demo.local | 所有业务编辑、计算、推荐、签核冻结、审计 |
| analyst / 工艺工程师 | analyst@demo.local | 方案与样本新增/修订、提交计算、起草推荐、建批/封批/拆盲；不能签核 |
| viewer / 只读观察员 | viewer@demo.local | 查看各模块、下载已完成结果、查看盲测完整性；不能编辑或查映射 |
| external / 外协检测员 | external@demo.local | 仅收取匿名清单并回传拉力；无其他接口权限 |

四个演示账号密码均为 `Demo123!`。权限由后端 JWT 与数据库角色共同校验；前端同步隐藏写入入口。

## 快速启动

```bash
cp .env.example .env
docker compose config --quiet
docker compose up -d --build
# 首次启动自动 seed，手动重复执行同样安全：
docker compose exec -T backend python -m scripts.seed_demo
```

访问 [前端](http://localhost:18204)、[后端 OpenAPI](http://localhost:19204/docs)。数据库映射 `localhost:17704`。五服务为 frontend、backend、worker、db、redis，均配置健康检查；后端与 worker 等待数据库和 Redis，前端等待后端。worker 每2秒检查队列与数据库待处理任务，处理后写数据库与共享产物卷。单 worker，重启时将中断任务恢复待执行。测试完成可 `docker compose down -v --remove-orphans`（删除本项目数据卷）。

Docker 默认网络池不足时使用独立可配置子网，默认 `10.253.105.0/24`；若与部署环境重叠，在 `.env` 修改 `NETWORK_SUBNET`。所有服务容器名基于 `COMPOSE_PROJECT_NAME`。

### 环境变量

| 变量 | 默认值 / 用途 |
|---|---|
| COMPOSE_PROJECT_NAME | seal-variance |
| FRONTEND_PORT / BACKEND_PORT / DB_PORT | 18204 / 19204 / 17704 |
| POSTGRES_PASSWORD | seal_local_pass，数据库凭据 |
| JWT_SECRET | 示例本地 JWT 签名密钥，可在 .env 替换 |
| SEED_DEMO | true，启动时执行幂等 seed；失败记日志而不阻塞服务 |
| ARTIFACTS_DIR | /app/artifacts，worker 结果产物目录（本地开发可改指） |
| NETWORK_SUBNET | 10.253.105.0/24 |

## 技术与本地开发

| 层 | 技术 |
|---|---|
| 前端 | 原生 HTML、CSS、JavaScript ES modules，Nginx 1.27 |
| 后端 | Python 3.11、FastAPI 0.115.6、SQLAlchemy 2.0.36、PyJWT |
| 计算 | SciPy 1.14.1 F 分布尾概率；其余方差分解由 Python 实算 |
| 队列/数据 | Redis 7、PostgreSQL 16 |

前端无构建步骤。后端可在 `backend/` 创建虚拟环境并安装 `requirements.txt`，设置 `DATABASE_URL`、`REDIS_URL`、`JWT_SECRET` 后运行 `uvicorn src.main:app --reload`，另开终端 `python -m src.worker`。开发时前端请求 `/api/`，Nginx 去掉此代理前缀；直接访问后端时路由不带 `/api`。数据库启动时由 SQLAlchemy 建表，`backend/migrations/001_initial.sql` 提供同等初始 DDL。

## 算法口径与失败态

输入为选定工艺与材料批次的全部有效拉力样本（单位 N，0 < N ≤ 200）。组数 2–8，每组至少2条；选重复工艺或不存在的方案时直接拒绝请求，样本不足时后台任务记为 failed，不静默移除小样本组。`lot=全部` 会跨材料批次合并，需工程师先确认可比性。

对 k 组、总样本数 N，整体均值为 x̄，组均值为 x̄ᵢ：

- SS_between = Σ nᵢ(x̄ᵢ − x̄)²；SS_within = ΣΣ(xᵢⱼ − x̄ᵢ)²。
- SS_total = SS_between + SS_within，df_between = k−1，df_within = N−k。
- F = (SS_between / df_between) / (SS_within / df_within)。
- p = SciPy F 分布 survival function；保留完整浮点，前端极小值科学计数法展示。
- η² = SS_between / SS_total，组均值差异的整体检验阈值 α=0.05。

组内方差为零（SS_within ≤ 1e−12）时明确失败，避免无穷 F 进入 JSON。所有标记异常的样本仍纳入；修订测量只影响新任务。结果保存组别 n、均值、样本标准差、最小/最大、异常标记数、所有平方和/自由度/均方与输入 SHA-256。

假设为独立样本、组内近似正态和方差齐性；本版不执行正态/方差齐性自动检验或事后多重比较，因此整体显著不说明具体哪两组不同。推荐需人工考虑产品下限、外观、热损伤与能耗，并安排验证。只有本次比较中的工艺可被推荐。签核需先有完整推荐；签核后评议不可覆盖，新建任务留痕。

## Seed 与一天的工作剧本

随机种子 `3105`。自然键为用户邮箱、工艺编号、样本编号、评议标题、盲测批号；已有对象不覆盖，重复 seed 不增行、不覆盖用户修改。初始4账号、3方案、105样本、1个待执行评议（worker 真实计算）、1个开放中的盲测样批 `BB-DEMO`（HC-S1/HC-S2 各3条试条，可用外协账号演练回传）。

| 方案 | 温度 ℃ | 保压 s | 压力 MPa | 样本 |
|---|---:|---:|---:|---:|
| HC-S1 稳温基线 | 160 | 0.80 | 0.32 | 35 |
| HC-S2 延时封合 | 160 | 1.20 | 0.32 | 35 |
| HC-S3 升温短封 | 175 | 0.65 | 0.32 | 35 |

1. 08:50 观察员查看材料批次 `HC-1115` 的三方案台账。
2. 09:00 工程师核对 `HC-S1` 参数 160℃ / 0.8s / 0.32MPa。
3. 09:10 在 HC-S1 下录入 `HC-S1-036`，批次 HC-1115，最大拉力 23.40N。
4. 09:20 核对首件异常标记；本版保留该样本并在说明中解释。
5. 09:30 在方差分析选择 HC-S1、HC-S2、HC-S3 与 HC-1115，标题为“HC-1115 封合参数复核”。
6. 09:40 等待后台完成，核对平方和守恒、F/p/η²与组别标准差。
7. 10:00 起草推荐 HC-S2，说明额外保压时间可能增加能耗，需继续验证外观和封口完整性，不能只根据 p 值选型。
8. 10:10 负责人登录，检查推荐理由后签核，评议冻结。
9. 10:20 观察员下载 `seal-variance-<id>.json`，包含快照与签核者，交给试产负责人。

## 目录与共享枚举

```
frontend/src/  api / stores / types / components/common / hooks / pages / router / utils / constants
backend/src/   routes / controllers / services / models / schemas / middlewares / utils / constants / config
backend/scripts/seed_demo.py
backend/migrations/001_initial.sql
```

共享枚举为 ROLES 与 TASK_STATUS/STATUS、BLIND_STATUS：后端 `src/constants/enums.py`，认证判断在 `src/utils/security.py`，状态在 `src/services/assessments.py`、`src/services/blind.py` 与 `src/worker.py`；前端 `src/constants/enums.js`、`src/components/common/status.js`、`src/app.js`。角色枚举 admin/analyst/viewer/external；任务状态 queued/running/completed/failed，另有 approved 布尔业务状态；盲测批状态 open/sealed/unblinded。

## 盲测验证

`test-artifacts/blind-2611/verify_blind.py` 对运行中的后端执行 57 项端到端断言：匿名清单不泄露映射、越权查映射（外协/只读 403）、错号/重复整批拒绝、同值幂等与异值 409、缺测不给结论、封批并发争抢恰一次成功、回传与封批并发同一边界（5 轮无撕裂）、转入冲突整批回滚且重试不重复入样建评议、拆盲后迟到回传不改结果、归组入库与 ANOVA 数值核对、原有样本入口回归。`smoke_frontend.mjs` 用 Node 桩 DOM 渲染各角色页面。两者结果存于同目录 results 文件。

## 已知范围

小型项目逐条登记，不含 Excel/CSV 批量导入、删除、分页、自动取样设备连接、事后多重比较或外部电子签名。评议是本地数据库签核。时间戳以 UTC 留痕。前端字体从 Google Fonts 加载，离线时使用指定 serif 回退；核心业务不依赖字体服务。测试脚本、截图与 TESTING.md 位于批次 `test-artifacts/gb-3105/`，源码目录不存放这些证据。

MIT License，见 LICENSE。
