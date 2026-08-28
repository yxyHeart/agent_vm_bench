# XLSX 性能优化工作交接简报

> 交接目标:让另一个 agent 在无前置上下文下接手 XLSX 链路性能优化工作。
> 遵循方法论:`/Users/yxy/Documents/performance-optimization-methodology.md`(7 阶段:测量→分析→埋点→benchmark→profiling→优化→验证)。

---

## 1. 项目背景

**agent_vm_bench** — 虚拟化/沙箱场景的性能测试框架。两层代码:

| 层 | 位置 | 状态 |
|----|------|------|
| **新内核(推荐,forward)** | `src/bench_core/`(kernel)+ `src/env_provider/`(provider 契约) | 持续开发,~270 单测 |
| 冻结 legacy | `e2b_bench/`、`docker_bench/`、OpenStack(`vm_bench/`、`auto_vm_test.py`) | 原样保留,零共享 |

- 入口:`bench-core`(`bench_core.bench:main`),`--provider {fake,e2b,docker}`,`--config config/common/*.yaml`。
- 一份 `config/common/*.yaml` 同时带 `e2b:`+`docker:` 块,`--provider` 选读哪个。
- **document 工作流**:`workflow_type: document`,`case_kind: pdf|xlsx`;runner 把录制的"场景配方 JSON"逐条 replay 到沙箱(每次 `provider.exec`)。

本次任务聚焦 **docker 后端 + xlsx case** 的工具调用链路性能优化。

## 2. XLSX 工作流是什么

- **镜像** `ubuntu-document-bench:24.04-linuxarm64`:LibreOffice/Poppler/Python + 种子数据(2.96M 行 TLC 出租车)+ 助手脚本 + `document-bench-validate` 就绪探针。`CMD sleep infinity`(无端口,就绪=跑 `document-bench-validate` exit 0)。
- **配方 JSON**:`dockerfile_build/document/assets/operations/xlsx_key_operations.json`(schema `scene-key-operations-v2`,4 阶段 15 工具调用)。**在宿主机 repo 里读,不在镜像里**——所以 j 上必须有 repo checkout。
- **runner**:`src/bench_core/task_runner/document.py`(`DocumentOperationExecutor.execute` 回放)。
- 单任务实测 **~257.5s**。

## 3. 环境信息

### 本机(Mac,darwin/arm64)
- repo:`/Users/yxy/Desktop/agent_vm_bench`(含已加的埋点 + bugfix,见 §5)。
- 文档:`docs/xlsx-*.md`(见 §6)。

### 远程 `ssh j`(SSH 别名可用,`-o BatchMode=yes`)
- 架构 aarch64,Python 3.11.6,Docker 29.4.1(docker 免 sudo)。
- 镜像 `ubuntu-document-bench:24.04-linuxarm64`(709MB,已构建,`document-bench-validate` exit 0 验证过)。
- **自洽工作区 `~/yxy/document-bench/`**:repo + venv + results 全在一处(editable 安装指向本目录,recipe 从此处解析)。
- 旧冗余 `~/agent_vm_bench/`(repo+venv 已迁走,**待你确认 `rm -rf` 删除**)。

## 4. 运行命令(从 `~/yxy/document-bench`,全相对路径)

```bash
ssh j
cd ~/yxy/document-bench
# fake 烟囱(无 docker,验配置+preflight+recipe):
venv/bin/bench-core --provider fake --config config/common/document-xlsx.yaml --create-only -n 1
# docker 三步:
venv/bin/bench-core --provider docker --config config/common/document-xlsx.yaml --create-only -n N
venv/bin/bench-core --provider docker --config config/common/document-xlsx.yaml --detect --test-duration D
venv/bin/bench-core --provider docker --config config/common/document-xlsx.yaml --cleanup
```

- 配置:`config/common/document-{xlsx,pdf}.yaml`(本任务新建,Mac+j 都有)。`docker.image=ubuntu-document-bench:24.04-linuxarm64`,2vCPU/4g,前缀 `doc-bench-xlsx`/`doc-bench-pdf`(互不为前缀,避免 --cleanup 互杀)。
- CLI flag:**`--round-count`/`--round-size`/`--test-duration`**(无短参 `-rc/-rs`,那是 legacy e2b_bench 的)。
- 镜像 tag 必须与 config `docker.image` 完全一致。

## 5. 已应用的代码改动(repo,Mac+j 已同步)

### Bugfix A:docker exec 走 shell(关键)
`src/env_provider/docker/__init__.py` 的 `DockerProvider._exec`(~line 223):
```python
result = state.docker_container.exec_run(["sh", "-c", command], user="root", demux=True)
```
原为 `exec_run(command,...)`(按空白切分、不走 shell),导致 document runner 的 `&&` 链/heredoc 全报 `test: extra argument '&&'`。改后 document 工作流才跑通。

### Bugfix B:per-call 埋点(纯增量)
`src/bench_core/task_runner/document.py` 的 `_execute_phase`:每个 tool call 套 `perf_counter`,append `{phase, idx, fn, wall_ms, ok}` 到 `self._call_timings`;`execute()` finally 日志 `[CALLTIMINGS] <json>`。
- 保真:命令/控制流/输出不变,仅加 2× perf_counter + dict append。
- 抽数:`grep '\[CALLTIMINGS\]' log` → 每任务 15 条 JSON。

## 6. 已产出文档(本机 `docs/`)

- `xlsx-tool-call-chain.md` — 15 次工具调用链路(去外壳)。
- `xlsx-test-points.md` — 15 测试点表(TP-01..15)。
- `xlsx-e2e-timing.md` — per-call 实测耗时 + 阶段小计 + 根因分析。
- `xlsx-optimization-plan.md` — 已验证的优化方案。

## 7. 实测数据(1 任务,数据稳定)

总 **257.5s**。15 测试点(摘要,详见 `xlsx-e2e-timing.md`):

| TP | 阶段 | 耗时 | 操作 |
|----|------|-----:|------|
| TP-04 | P01 | 29.7s | openpyxl 全量 load(查结构) |
| TP-05 | P01 | 25.6s | openpyxl load+save(加图表) |
| TP-07 | P02 | 51.0s | run_xlsx_helper_atomic(load+改+save) |
| TP-08 | P03 | **62.6s** | **LibreOffice recalc**(负载本身) |
| TP-09 | P03 | 20.9s | openpyxl load(data_only=False) |
| TP-10 | P03 | 20.5s | openpyxl load(data_only=True) |
| TP-12 | P03 | 1.7s | export_csv(read_only 流式) |
| TP-13 | P04 | 24.5s | openpyxl load(verify) |
| TP-14 | P04 | 20.6s | openpyxl load(summary) |
| 其余(TP-01/02/03/06/11/15) | — | ~0.4s | 小 I/O |

**占比**:openpyxl 全量 load 7 次 = **192.7s(74.8%)**;LibreOffice recalc = 62.6s(24.3%);其余 0.9%。

## 8. 根因(纠正"recalc 是瓶颈"的直觉)

- **openpyxl 占 75%** = 纯 Python 全量物化(每 Cell 一个 Python 对象)× **冗余 7 次**(跨进程无复用)× 百万行规模。慢的是"物化整表"非"读文件"(TP-12 read_only 1.7s vs 全量 20.9s,12× 差距)。
- **LibreOffice 占 24%** = 任务本身就是百万行公式重算,C++ 实现已相对高效,优化它 = 改变被测负载,**不在范围**。

## 9. 已验证的优化方案(详见 `xlsx-optimization-plan.md`)

read_only 限制:只支持读值 + `merged_cells`;**不支持** `_charts`/`comment`/`conditional_formatting`/`data_validations`/`freeze_panes`/`_external_links`,且不支持 `ws.cell(r,c)`(须 `iter_rows()`)。

| # | 优化 | 改法 | 省 | 风险 |
|---|------|------|---:|------|
| **1** | TP-09/10 切 read_only | P03 两条 `python3 -c`:加 `read_only=True`,`ws.cell()`→`iter_rows()` | ~37s(−14%) | 低(只读,输出一致) |
| **2** | 合并 TP-13+14 全量 load | P04 两脚本合一,一次 full load 同时 verify+summary | ~20s(−8%) | 中(保 bit-for-bit) |

合计 **−22%**。

**不优化(数据背书)**:per-call docker exec 税 ~5.4s(2.1%)→ 持久会话模型不做;TP-04/05/07/13/14 取 features 或需写 → inherent;TP-08 负载本身。
**架构级备选**:换 Rust 后端 `python-calamine`(比 openpyxl 快 5-10×),大改,先做 #1/#2 再评估。

## 10. 操作经验/坑

- **长任务别用 `| tail`**:tail 要 EOF 才输出,长跑被误判"挂起无输出"。用后台+日志:`setsid cmd </dev/null >/tmp/x.log 2>&1 &` 再轮询 `tail /tmp/x.log`。
- **`pkill -f bench-core` 会自杀**(承载命令的 shell 命令行含 "bench-core")。用 `ps -eo pid,cmd | grep '[b]ench-core --provider' | awk '{print $1}' | xargs kill`(方括号 trick 防自匹配)。
- **bench-core detect 模式报告生成后会短暂 lingering**(不立即退出,结果已存),`kill <pid>` 或等自退。
- **容器前缀别互为前缀**:`doc-bench-pdf` vs `doc-bench-xlsx`(非 `doc-bench`,否则 `--cleanup` 误杀)。
- j 上 `rg` 没装,用 `grep`。

## 11. 待办(next steps)

1. **实施优化 #1**(TP-09/10 切 read_only)→ 重测 per-call 验证 −14% 且输出一致(P04 verify 仍 `status=success`)。
2. **实施优化 #2**(合并 TP-13/14)→ 重测验证 −8%。
3. 确认后 `rm -rf ~/agent_vm_bench`(冗余)。
4. 评估架构级 `python-calamine`(可选)。
