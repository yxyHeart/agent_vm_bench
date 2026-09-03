# XLSX 最终报告

## 一、调用链

### 1.1 外层框架说明

外层(`run_benchmark` / `RoundRobinTaskManager` / `DocumentRoundRunner` / `StatsCollector` / 配方加载等)只是 ​**bench-core 的框架外壳**​——一个模拟 agent 按固定剧本回放工具调用、外加评测仪表,用于造可复现负载。​**无需关心它的时间**​,真 agent 接进来这层会整体替换。本报告只聚焦里面真实 agent 会走的 ​**15 次工具调用**​。

> 前置(外壳做的,不计入 15):`prepare_workspace` 把种子 `cp -a /opt/document-bench/xlsx → <WS>` 并建 `output/`,使每次任务起点一致。
> `<WS>` = `/root/.openclaw/workspace/tool-modeling/SUB-MEM-OFFICE-01`(容器内工作区)。

### 1.2 15 次工具调用

#### P01 inspect_prepare — 检查与准备

| # | 函数 | 执行命令                                                                                                                                       | 做什么                                         |
| --- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------ |
| 1 | read | `test -f /SKILL.md && head -c 65536 /SKILL.md >/dev/null`                                                                                  | `test` xlsx SKILL.md                   |
| 2 | exec | `cat /input/verify_xlsx_enhanced.py`                                                                                                       | `cat`校验脚本源码                          |
| 3 | exec | `cp /input/monthly_operations_template.xlsx /output/monthly_operations_report.xlsx`                                                        | `cp`模板→工作副本                         |
| 4 | exec | `cd && python3 -c "from openpyxl import load_workbook; wb=load_workbook('input/...template.xlsx', data_only=False); print('Sheets: ...')"` | `openpyxl` load 检查结构(各表行数/列数/前 24 行预览) |
| 5 | exec | `cd && python3 <<'PYEOF' …openpyxl 只读检查…`                                                                                              | `openpyxl` load 检查图表/单元格格式/数据校验/条件格式(只读,不修改)      |

#### P02 build — 增强

| # | 函数  | 执行命令                                                                                                                        | 做什么                                                        |
| --- | ------- | --------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| 6 | write | `mkdir -p `+ base64 heredoc 写`enhance_workbook.py`(10KB)                                                               | `write` 写py脚本            |
| 7 | exec  | `cd && python3 /opt/document-bench/bin/run_xlsx_helper_atomic.py enhance_workbook.py output/monthly_operations_report.xlsx` | `openpyxl` load + save |

#### P03 process_publish — 重算与导出(最重)

| #  | 函数 | 执行命令                                                                                                     | 做什么                                                         |
| ---- | ------ | -------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| 8  | exec | `cd && python3 /root/.openclaw/skills/xlsx/scripts/recalc.py output/monthly_operations_report.xlsx 180 > output/formula_recalc.json`                                     | 脚本内 `openpyxl` load × 2(数公式/取重算值)+ soffice 重算   |
| 9  | exec | `cd && python3 -c "openpyxl.load_workbook('...report.xlsx', data_only=False)…"`                                                                                         | `openpyxl` load_workbook(data_only=False)读公式             |
| 10 | exec | `cd && python3 -c "openpyxl.load_workbook('...report.xlsx', data_only=True)…"`                                                                                          | `openpyxl` load_workbook(data_only=True)读计算值            |
| 11 | exec | `cat /output/formula_recalc.json`                                                                                                                                        | `cat`重算结果 JSON                                         |
| 12 | exec | `cd && python3 /opt/document-bench/bin/export_xlsx_csv.py output/monthly_operations_report.xlsx output/monthly_operations_summary.csv output/reconciliation_summary.csv` | `python`导出 Executive + Reconciliation 两 CSV |

#### P04 verify_deliver — 校验与交付

| #  | 函数 | 执行命令                                                                                                                                   | 做什么                                                    |
| ---- | ------ | --------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| 13 | exec | `cd && python3 input/verify_xlsx_enhanced.py output/monthly_operations_report.xlsx output/formula_recalc.json output/business_verification.json output/monthly_operations_summary.csv output/reconciliation_summary.csv` | `openpyxl` load, 业务校验出 business_verification.json |
| 14 | exec | `cd && python3 /opt/document-bench/bin/write_xlsx_summary.py output/monthly_operations_report.xlsx output/business_verification.json output/formula_recalc.json output/xlsx_enhancement_summary.json output/monthly_operations_summary.csv output/reconciliation_summary.csv` | `openpyxl` load, 汇总特征/sha256→xlsx_enhancement_summary.json |
| 15 | exec | `cd && test -s …(六个交付物)… && python3 -c "…assert 三份 JSON 状态为 success…"`                                                            | `test`+断言: xlsx/两 CSV/formula_recalc/business_verification/xlsx_enhancement_summary 六文件非空, 且三份 JSON 的 status/failures 通过 |

## 二、测试点说明

测试点 = 上面工具调用链路里的 15 次调用,每次调用即一个测试点。外层框架不计。

## 三、各阶段耗时

> 以下数据跑在蓝区的 920B 服务器。

### 数据来源与运行记录

本节及第四节全部数据为 **2026-09-03 19:32–20:00 同一窗口、同一宿主机背靠背采集**:

| 组 | 镜像 | 运行报告(results/document/xlsx/) | 任务数 n | Avg Latency | Success |
|----|------|----------------------------------|:---:|------:|:---:|
| stock | ubuntu-document-bench:24.04-linuxarm64 | document_xlsx_bench_20260903_194203.txt | 1 | 257.5s | 1/1 |
| speedups | ubuntu-document-bench:speedups | document_xlsx_speedups_bench_20260903_195407.txt | 1 | 217.0s | 1/1 |
| disk-cache | ubuntu-document-bench:disk-cache | document_xlsx_diskcache_bench_20260903_195025.txt | 1 | 170.6s | 1/1 |
| combo | ubuntu-document-bench:xlsx-combo | document_xlsx_combo_bench_20260903_193738.txt | 2 | 143.0s | 2/2 |

- 运行模式均为 **round_robin**(test.duration=160s 等,见 `config/common/document-xlsx-*.yaml`):stock 单任务 257.5s 超过窗口时长,仅完成 1 个任务;combo 单任务 ~150s,窗口内完成 2 个任务(第 2 个任务因模板缓存条目跨任务复用更快,见 4.3)。**combo 的 Avg 143.0s 是 2 任务均值(153.0s + 132.3s),冷对冷单任务口径为 153.0s。**
- 逐调用数据取自运行日志的 `[CALLTIMINGS]`(per-tool-call 计时);调用合计与任务 Avg 的差为调用间开销(零头 <1s)。
- 样本量说明:n=1/1/1/2,单次观察;历史窗口(8/31、9/1、9/3 上午)同配置结果与本窗口一致(stock 257.9–258.7s / speedups 217.9–218.2s / disk-cache 165.5–170.6s / combo 143.1–144.4s),互为佐证,未纳入正文表格。样本量不足以给出 P50/P95 置信区间,本文所有百分比为单次运行口径。
- 原始日志已留档:`docs/runlogs/xlsx-20260903/`(四组完整 bench 运行日志,含 `[CALLTIMINGS]` 逐调用计时,与四份运行报告 txt 一一对应)。
- 容器规格 2核4G(`cpu_limit: 2.0`, `memory_limit: 4g`),单任务串行。

### e2e 耗时

#### 15 个测试点实测(stock,2026-09-03 19:42 运行)

| TP    | 阶段                  | 函数    |     耗时 |    占比 | 操作描述                                          |
| ----- | ------------------- | ----- | -----: | ----: | --------------------------------------------- |
| TP-01 | P01 inspect_prepare | read  | 0.05s |  0.0% | `test` xlsx SKILL.md                          |
| TP-02 | P01 inspect_prepare | exec  | 0.05s |  0.0% | `cat` 校验脚本源码                                  |
| TP-03 | P01 inspect_prepare | exec  | 0.06s |  0.0% | `cp` 模板→工作副本                                  |
| TP-04 | P01 inspect_prepare | exec  | 30.11s | 11.7% | `openpyxl` load 检查结构                          |
| TP-05 | P01 inspect_prepare | exec  | 25.59s |  9.9% | `openpyxl` 只读检查图表/格式                          |
| TP-06 | P02 build           | write | 0.19s |  0.1% | `write` 写 py 脚本                               |
| TP-07 | P02 build           | exec  | 50.93s | 19.8% | `openpyxl` load + save                        |
| TP-08 | P03 process_publish | exec  | 62.11s | 24.1% | 脚本内 `openpyxl` load × 2 + soffice 重算          |
| TP-09 | P03 process_publish | exec  | 20.78s |  8.1% | `openpyxl` load_workbook(data_only=False) 读公式 |
| TP-10 | P03 process_publish | exec  | 20.49s |  8.0% | `openpyxl` load_workbook(data_only=True) 读计算值 |
| TP-11 | P03 process_publish | exec  | 0.11s |  0.0% | `cat` 重算结果 JSON                               |
| TP-12 | P03 process_publish | exec  | 1.71s |  0.7% | `python` 导出 Executive + Reconciliation 两个 CSV |
| TP-13 | P04 verify_deliver  | exec  | 24.46s |  9.5% | `openpyxl` load, 业务校验出 verification.json          |
| TP-14 | P04 verify_deliver  | exec  | 20.51s |  8.0% | `openpyxl` load, 汇总特征/sha256→JSON      |
| TP-15 | P04 verify_deliver  | exec  | 0.10s |  0.0% | `test`+断言六交付物                          |
| **合计** | | | **257.25s** | 100% | (任务级 Avg Latency 257.5s, 含调用间开销) |

#### 阶段小计

| 阶段 | 耗时 | 占比 |
|------|-----:|-----:|
| P01 inspect_prepare | 55.86s | 21.7% |
| P02 build | 51.12s | 19.9% |
| P03 process_publish | 105.20s | 40.9% |
| P04 verify_deliver | 45.07s | 17.5% |
| **总计** | **257.25s** | 100% |

### openpyxl 热点分析

> 被测命令:`venv/bin/python -c "from openpyxl import load_workbook; wb=load_workbook('/tmp/xlsx_template.xlsx', read_only=False); wb.close()"`,分别套 `perf stat`/`perf record -F 997 -g`/`strace -c -f`。
> 数据集:跑的是**种子模板**(从镜像提取到宿主 `/tmp`),代表 TP-04 的全量 load;TP-09/10 读的是重算后的 report.xlsx(同量级,文件结构略异)。

**数据规模口径**(实测锚定):源 Parquet 2.96M 行,模板脚本抽样 **100,000 数据行 × 25 列**写入主表 Raw_Sample(含表头 100,001 行);全簿非空格 **2,501,211** 个;压缩 xlsx **12.3MB**,解压合计 123.6MB(其中主表 sheet1.xml **123.5MB**)。下文统一用"**10 万行主表 / 250 万格**"口径。

#### perf stat

| 指标 | 值(访问数 / miss 数) | 比率 | 解读 |
|------|------|------|------|
| cycles | 76.05B | — | — |
| instructions | 190.42B | IPC 2.50 | 高吞吐 |
| cache-references / misses | 74.5B / 1.31B | **1.76%** | 低 |
| branch-instructions / misses | 37.04B / 262M | **0.71%** | 低 |
| L1-dcache loads / misses | 74.1B / 1.30B | **1.76%** | 低 |
| L1-icache loads / misses | 27.6B / 1.59B | **5.75%** | 中(最高,指令 cache) |
| dTLB loads / misses | 83.5B / 2.69B | **3.22%** | 中 |
| iTLB loads / misses | 27.8B / 87.6M | **0.32%** | 低 |

**结论(限于当前计数器):** IPC 2.50、各 miss 率低,**当前 PMU 计数器未显示出明显的 cache/分支/TLB 瓶颈**;主要成本更可能是解释器**指令总量巨大**(190.42B 条 ÷ 250 万格 ≈ **76K 指令/格**)= 纯 Python 逐 Cell 物化的解释器开销。user(26.18s)≈ elapsed(26.74s)→ 单线程打满一个核。(IPC>1 不排除前端/后端管线存在局部 stall,但结合 libpython 占 87% 的采样构成,指令量是第一性解释。)

#### cProfile 热点函数(纯 Python 层,perf record 看不到的)

perf record 只能采 native 符号(libpython 87% + 一堆 `0x...`),**解不出 Python 帧名**。用 `venv-clean/bin/python -m cProfile -s cumulative /tmp/cprof_load.py`(`/tmp/xlsx_template.xlsx`, data_only=False)直接点名热点函数。按 **tottime(自身耗时,不含子调用)** 排,取 top 20:

| # | 函数 | tottime | 调用 | 模块 |
|---|------|------:|----:|------|
| 1 | `XMLParser.feed`(expat C) | 8.92 | 7.6K | xml.etree.ElementTree |
| 2 | `parse_cell` | 5.95 | 2.5M | openpyxl/_reader.py:189 |
| 3 | `bind_cells` | 3.82 | 7 | openpyxl/_reader.py:367 |
| 4 | `from_tree` | 2.45 | 801K | openpyxl/serialisable.py:46 |
| 5 | `read_events` | 2.36 | 5.9M | xml.etree.ElementTree |
| 6 | `coordinate_to_tuple` | 2.26 | 2.5M | openpyxl/utils/cell.py:206 |
| 7 | `parse`(分派器) | 2.04 | 100K | openpyxl/_reader.py:125 |
| 8 | `sequence.__set__` | 2.04 | 1.6M | openpyxl/descriptors/sequence.py:24 |
| 9 | `Cell.__init__` | 1.80 | 2.5M | openpyxl/cell/cell.py:108 |
| 10 | `isinstance` | 1.25 | 13M | built-in |
| 11 | `StyleableObject.__init__` | 1.14 | 2.5M | openpyxl/styles/styleable.py:132 |
| 12 | `text.__init__` | 1.06 | 800K | openpyxl/text.py:161 |
| 13 | `iterator` | 0.99 | 5.9M | xml.etree.ElementTree |
| 14 | `Element.get` | 0.83 | 7.5M | xml.etree.ElementTree |
| 15 | `__new__` | 0.71 | 2.5M | built-in |
| 16 | `parse_row ` | 0.70 | 100K | openpyxl/_reader.py:303 |
| 17 | `base.__set__` | 0.68 | 3.2M | openpyxl/descriptors/base.py:24 |
| 18 | `localname` | 0.65 | 801K | openpyxl/xml/functions.py:77 |
| 19 | `Element.find` | 0.64 | 3.3M | xml.etree.ElementTree |
| 20 | `nested.__set__` | 0.63 | 801K | openpyxl/descriptors/nested.py:26 |

> **口径注意:** cProfile 的 tottime 含埋点开销,其总和远超无埋点的真实 wall time(26.7s),**绝对秒数不可加总、不可与 wall time 对照,只有相对排名可信**。按模块归属做相对比较:XML 解析系(expat/ElementTree 帧约 14.4s)与 openpyxl 对象构造系(约 24.6s)的 tottime 量级比约为 **4 : 6**——即瓶颈重心在"Element 树 → Cell 对象"的模型转换,而非 XML 语法解析本身。

#### strace -c -f(系统调用)

每个 syscall 实际耗时及其占 openpyxl load(26.7s)的比例:

| syscall | 耗时 | 占运行(26.7s) |
|---------|-----:|---------------:|
| munmap | 18ms | 0.07% |
| newfstatat | 0.6ms | 0.002% |
| read | 0.36ms | 0.001% |
| openat | 0.2ms | 0.001% |
| mmap | 0.2ms | 0.001% |
| 其余(lseek/close/…) | <0.2ms | ~0 |
| **合计** | **~20ms** | **0.07%** |

**结论:99.93% 是 user CPU,syscall 只占 0.07%。** read 0.36ms(I/O 几乎为零,12.3MB 压缩 xlsx 一次读入,123.5MB 解压在进程内 CPU)。对象分配走 pymalloc 内存池不每对象 mmap,故 mmap/munmap 都是 arena 级、次数少。→ 非 I/O、非 syscall,纯 user CPU,strace 对这场景信号极少,真信号在 perf。

#### XLSX 基准优化前耗时分析: openpyxl 读写盘点

> 对全部 recipe 命令与冻结脚本源码逐一盘点(含脚本内部, 按实际执行路径计):

```text
全量 load_workbook ×9:
  TP-04 模板(结构)   TP-05 副本(图表)   TP-07 增强输入
  TP-08 ×2 重算后查错误(data_only=True) + 数公式(False)
  TP-09 读公式       TP-10 读值         TP-13 校验(verify_formula_workbook, 可编辑 1 次)
  TP-14 汇总
read_only 流式 ×3:  TP-12 导 CSV ×1 + TP-13 校验内 ×2   (1.7s 级, 忽略)
Workbook.save   ×1:  TP-07 增强输出(全流程唯一写)
```

关键结构: **同一份 12.3MB / 10 万行主表 / 250 万格工作簿被完整解析 9 次**, 每次都是
独立 `python3` 进程(`docker exec`), 内存对象树用完即弃, 跨调用零复用。

#### openpyxl 占 E2E 耗时

E2E(stock, n=1)Avg Latency 257.5s。"openpyxl 占比"给出两个口径,不再给单一百分比:

| 口径 | 计算 | 结果 | 说明 |
|------|------|------|------|
| 调用级(实测) | 8 个含全量 load 的调用合计(TP-04/05/07/08/09/10/13/14) | **255.0s / 99.1%** | 上界口径:内含 soffice 重算 ~16s、约 10 个 python 进程启动、各脚本自身逻辑(遍历/校验/打印) |
| 微基准外推(估算) | 单次冷 load 微基准 22.3s × 9 + save ~25s | **≈ 226s / ~88%** | 下界口径:扣除调用内非 openpyxl 部分 |

两个口径互为印证:**"openpyxl 全量加载主导端到端"结论稳固**,精确数值取决于口径。

## 四、优化点尝试

### 4.1 多次读取相同内容 -> 构建 xml 缓存

> 报告地址：https://wiki.huawei.com/domains/101868/wiki/272348/WIKI2026082712490869

#### 背景

XLSX 文档基准(2核4G 容器, 单任务)优化前端到端 **257.5s**。对全部 recipe 命令与冻结脚本逐一盘点后, 瓶颈高度集中: **同一份 12.3MB 压缩 / 10 万行主表 / 250 万格的工作簿被完整解析了 9 次**(全量 `load_workbook` ×9), 每次都是独立 `python3` 进程, 内存对象树用完即弃、跨调用零复用。按上一节两个口径, openpyxl 主导 E2E 的 88%~99%; 其余是 LibreOffice 重算 ~16s(负载本身)与杂项 I/O ~2s。

也就是说: 这个流程最大的开销不是"算", 而是同一份数据被反复"读进来建对象、用一下、扔掉"。

#### 方案

##### 思路:跳过重复的 XML 解析

openpyxl 把一个 .xlsx 读进内存,大致分两段(cProfile 相对量级,见口径注意):

1. **XML 解析段**:把文件里的 XML 读成 Element 树,逐个单元格抽出值/类型/样式(expat/ElementTree 系,相对占比约四成)。
2. **单元格构造段**:把这些数据组装成 250 万个单元格对象,放进工作表(openpyxl 对象系,相对占比约六成)。

同一个文件被加载多次时,只有第一次需要解析;后续完全可以把第一次的结果存下来复用——**跳过 XML 解析段,只保留对象构造段(无法再省,因为 250 万个对象必须造)**。这就是缓存的全部意义。

#### 最终数据

##### 端到端(2026-09-03 19:32–20:00 同窗口 A/B, round_robin, n=1)

| 指标 | 优化前(stock) | 仅加缓存 | Δ |
|------|----:|----:|----:|
| Avg Latency | 257.5s | **170.6s** | **-33.7%** |
| Success Rate | 1/1 | 1/1 | — |

##### 逐调用(同一次运行的 [CALLTIMINGS])

| 调用 | 优化前 | 缓存后 | 机制 |
|------|----:|----:|------|
| TP-04 结构检查 | 30.11s | 36.69s | 首次 MISS: 正常解析 + 落盘(多出的 ~6.6s 是快照提取/落盘成本, 一次性) |
| TP-05 格式检查 | 25.59s | **5.48s** | 模板副本与 TP-04 同内容 → 指纹直接命中 |
| TP-07 增强存盘 | 50.93s | **29.32s** | load 侧命中; save 走原生路径不变 |
| TP-08 重算+双读 | 62.11s | 69.74s | 重算后是新文件, 两次加载必然 MISS(各付一次落盘); soffice 部分不变 |
| TP-09 读公式 | 20.78s | **5.53s** | TP-08 落的盘, 命中 |
| TP-10 读值 | 20.49s | **5.52s** | 同上(另一视角的条目) |
| TP-13 业务校验 | 24.46s | **10.19s** | 命中 |
| TP-14 汇总特征 | 20.51s | **5.38s** | 命中 |

#### 验证范围与已知边界

本优化在以下范围验证通过(**不是通用语义等价证明**):

- 基准全链 15 步通过,含 TP-15 六交付物 + 三 JSON 状态断言;多轮稳定(stock/缓存/组合镜像各至少 1–2 任务)。
- 缓存命中重建后,cell 级指纹(值/类型/样式)与原生解析结果 bit-for-bit 一致(单点验证,详见 disk-cache 报告)。

已知边界(通用场景部署前需补测/修补):

1. **内容指纹 = 首尾各 4MB md5 + 文件大小**:中段字节改动且首尾与大小均不变时理论上不失效。zip 结构下内容改动通常也会改变中央目录/尾部字节,但不构成形式化保证。
2. **缓存键未包含 `rich_text`**:`rich_text=True` 的调用会错误命中默认条目(基准链路不使用该参数)。
3. **包装函数签名为 `(filename, data_only, ...)`**:第二个位置参数与原版 `load_workbook(filename, read_only, ...)` 不同,位置传参的调用方语义改变(基准链路全部关键字传参)。
4. **StyleArray 共享**:重建后 `cell._style` 共享 `wb._cell_styles` 池——与原生 `bind_cells` 行为一致(原生即 `style = ws.parent._cell_styles[sid]` 共享),非本优化引入的差异。

### 4.2 openpyxl speedups 扩展

> https://wiki.huawei.com/domains/101868/wiki/272348/WIKI2026083112558138

#### 背景: 钱花在哪

PMU 画像(此前已采集): 处理约 250 万 Cell 执行了 **~190B 条指令**, IPC 2.5, libpython 占 87%, libexpat 仅 6.5%, 当前计数器未见明显 memory stall、syscall 占比 0.07%。结论: 瓶颈不是"指令跑得慢", 是**每个单元格都在支付一套 Python 协议税**(对象分配/方法分发/中间 dict/字典查找)。

冷加载的一次拆解(发行版解释器): 纯 iterparse 无操作循环(仅 expat+Element 创建)对该 123MB sheet 实测 **~7.6s**——即 XML→Element 是地板, 其余全部是 Element→Cell 模型转换的 Python 开销。这就是优化对象。

#### 方案: openpyxl_speedups 扩展

##### 问题: 每个 Cell 的"Python 协议税"

openpyxl 原生加载一个 sheet 的链路:

```text
XML 字节 → expat(C) → Element 对象树 → Python 循环逐格处理 → Cell 对象
```

每处理一个格子(本工作簿 250 万次), Python 层要支付:

| 开销 | 次数 |
|---|---|
| `parse_cell()` 方法调用 + 返回值打包成 dict(5 个键) | 1 次/格 |
| `bind_cells()` 再从 dict 逐键取出 5 次 | 1 次/格 |
| `coordinate_to_tuple("AB123")`: 切片、反转、字典查找 | 1 次/格 |
| `element.find/findtext` 扫描子树 3 次(v/f/is 各一次) | 3 次/格 |
| `Cell.__init__` 构造 + 属性赋值 | 1 次/格 |
| 每格复制一份 StyleArray(正确性必需, openpyxl 样式是原地改) | 1 次/格 |

这些在 CPython 里全是解释器字节码: 对象分配、引用计数、方法分发、dict hash。250 万格 × 每格几十次解释器操作 = 190B 指令的主体。地板测量也印证: 纯 expat+Element 创建只要 7.6s, 冷加载却要 ~25s——多出的 ~17s 全是 Element→Cell 这一圈的 Python 协议税。

##### 优化: 把整个循环编译成 C

核心思想一句话: **Python↔C 的边界从"每格一次"变成"每个 sheet 一次"**。

**融合循环(bind_cells 整体替换)。** 原版 `bind_cells` → `parser.parse()` → `parse_row()` → `parse_cell()` 是四层 Python 调用, 中间用 dict 传值。加速版把四层全部内联进一个 Cython 编译的 C 循环:

```text
iterparse 流水线里:
  行标签到达 → 行计数/行维度副作用(逐行复刻原版)
  每个格元素 → 单遍扫描子元素(v/f/is 一轮拿全, 替代 3 次子树查找)
             → 坐标单遍解析(无切片/反转/字典)
             → Cell.__new__ 直填 7 个槽位
             → ws._cells[(row, col)] = cell
```

效果: 每格的**中间 dict 消失**(值直接走 C 局部变量)、**4 层方法调用消失**(循环体内是编译后的机器码)、**子树扫描从 3 遍变 1 遍**。

**GC 守卫(单项 -3.9s)。** 加载期间堆上持续增长到几百万个长命且无环的对象, 但 CPython 的循环 GC 每分配 700 个对象(gen0 阈值)就醒来把它们全部扫一遍——几乎收不到垃圾, 纯浪费。融合循环入口 `gc.disable()`、出口恢复, refcount 回收完全不受影响。

**语义等价(不是简化, 是搬运)。** 融合循环逐行复刻 openpyxl 3.1.5 的行为: date 格式的数值转换、共享字符串查找、inlineStr、公式判断、行维度副作用……全部调用 openpyxl 自己的同一批辅助函数。产物是原汁原味的 `openpyxl.cell.Cell`(`type(ws["A1"]) is Cell`)。版本门精确 `openpyxl == "3.1.5"`, 不符自动回退 stock。

#### 实测

##### 端到端(2026-09-03 19:32–20:00 同窗口 A/B, round_robin, n=1)

| 指标 | stock | speedups | Δ |
|------|----:|----:|----:|
| Avg Latency | 257.5s | **217.0s** | **-15.7%** |
| Success Rate | 1/1 | 1/1 | — |

逐调用(同一次运行的 [CALLTIMINGS]):

| 调用 | 内容 | stock | speedups | 降幅 |
|------|------|----:|----:|----:|
| TP-04 | 结构检查(冷加载) | 30.11s | 24.11s | -20% |
| TP-05 | 格式检查(冷加载) | 25.59s | 19.69s | -23% |
| TP-07 | 增强存盘 | 50.93s | 45.48s | -11% |
| TP-08 | 重算+双读 | 62.11s | 54.32s | -13% |
| TP-09 | 读公式 | 20.78s | 16.91s | -19% |
| TP-10 | 读值 | 20.49s | 16.91s | -17% |
| TP-13 | 业务校验 | 24.46s | 20.61s | -16% |
| TP-14 | 汇总特征 | 20.51s | 16.54s | -19% |

含 LibreOffice 的 TP-08 降幅来自该步骤中 soffice 前后的 openpyxl Python 处理; 存盘重的 TP-07 降幅里 load 侧贡献为主, save 侧走 stock 路径不变。

### 4.3 两个优化点结合(最终形态)

> 两层完全正交: 缓存救"重复解析"(9 次加载里 6 次纯重复, 命中后不碰 XML), speedups 救"每次解析的成本"(MISS 的 3 次冷解析走 C 融合循环)。**命中路径走缓存自己的 `_rebuild_cells` 重建(纯 Python 直填槽位), 不经过 speedups;speedups 只作用于 MISS 的冷解析。** 镜像里同时注入两层共 5 个文件(注入钩子已处理多 .pth 共存的导入顺序竞争: openpyxl 被任一钩子先导入, 另一钩子立即补 patch)。

#### 实测(2026-09-03 19:32–20:00 同窗口 A/B, round_robin)

| 指标 | stock (n=1) | 仅缓存 (n=1) | 仅 speedups (n=1) | **组合 (n=2)** |
|------|----:|----:|----:|----:|
| Avg Latency | 257.5s | 170.6s | 217.0s | **143.0s** |
| 相对 stock | — | -33.7% | -15.7% | **-44.5%** |
| 冷对冷单任务口径 | — | — | — | 153.0s(-40.6%) |
| Success Rate | 1/1 | 1/1 | 1/1 | 2/2 |

**口径说明:** combo 的 Avg 143.0s 是 2 任务均值(任务 1: 153.0s, 任务 2: 132.3s)。任务 2 更快的原因是**模板缓存条目跨任务复用**:工作区每任务重置,但容器内 `/tmp/oxlcache` 保留,任务 2 的 TP-04(加载模板)从 MISS 变 HIT(28.56s → 8.04s,见下表);重算输出因内容含时间戳类字节,指纹跨任务不重复(已实测两次重算输出指纹不同),任务 2 的 TP-08 仍为 MISS。与 stock(257.5s, 单任务)的同口径对比应看冷对冷 153.0s(**-40.6%**)。

#### 逐调用(任务 1, 冷缓存, 同一次运行的 [CALLTIMINGS]; 合计 153.03s)

| 调用 | 内容 | stock | 组合 | 时间去哪了 |
|------|------|----:|----:|------|
| TP-04 | 结构检查 | 30.11s | 28.56s | 首次 MISS: 解析被 speedups 砍 ~4s, 但要额外付快照提取/落盘成本——首次净省有限, 换来后续命中 |
| TP-05 | 格式检查 | 25.59s | **5.53s** | 副本与模板同内容 → 指纹命中: 解析整段消失, 只剩 ~4s 快照反序列化+重建 250 万 Cell + 打印 |
| TP-06 | 写增强脚本 | 0.19s | 0.27s | — (纯文件写入, 无优化空间) |
| TP-07 | 增强存盘 | 50.93s | **28.93s** | 50.9 ≈ load ~22 + 修改 ~4 + save ~25; load 侧命中只剩 ~4s(省 ~18s); save ~25s 原生路径两层都不碰(下一个优化点); 修改 4s 不变 |
| TP-08 | 重算+双读 | 62.11s | 61.01s | 62.1 ≈ soffice ~16 + 两次全量 load ~44 + 杂项; 重算改写了文件 → 指纹失效, 两次 load 都 MISS: 解析被 speedups 各省 ~4s, 但各付一次落盘 → 净变化 ≈ 0; soffice 16s 是负载本身 |
| TP-09 | 读公式 | 20.78s | **5.55s** | TP-08 的两次 MISS 已把两个视角的快照落盘 → 直接命中: 解析整段消失, 剩 ~4s 重建 + ~1.5s 读公式遍历 |
| TP-10 | 读值 | 20.49s | **6.62s** | 同上, 命中的是 data_only=True 视角的另一条快照 |
| TP-11 | 读重算 JSON | 0.11s | 0.11s | — (cat 一个小 JSON) |
| TP-12 | 导出 CSV | 1.71s | 1.74s | read_only=True 流式扫描, 本来就不建对象树——两层均不适用也无需适用 |
| TP-13 | 业务校验 | 24.46s | **8.80s** | 脚本内 1 次全量 load 命中(解析整段消失); 剩余 ~4s 重建 + ~4.5s 是 20+ 项 check 的校验逻辑本身(冻结脚本, 不动) |
| TP-14 | 汇总特征 | 20.51s | **5.48s** | 命中: ~4s 重建 + ~1.5s 特征收集/写 JSON |
| TP-15 | 断言交付 | 0.10s | 0.25s | — |

组合收益拆解(stock 257.25s → 组合任务 1 153.03s, 省 104.2s): **缓存是绝对大头**(6 次命中加载, 每次 20-30s 解析段消失); speedups 只作用于 3 次 MISS(各省 ~4s, 合计 ~12s), 其中 ~9s 被快照落盘成本部分抵销。任务 2 相对任务 1 再省 20.7s(TP-04 28.56→8.04s 模板条目跨任务命中, 其余调用一致)。

#### 任务 2 逐调用(模板缓存跨任务复用后, 合计 132.30s)

| 调用 | 任务 1 | 任务 2 | 差异 |
|------|----:|----:|------|
| TP-04 | 28.56s | **8.04s** | 模板缓存条目跨任务命中(容器内 /tmp/oxlcache 保留) |
| TP-05 | 5.53s | 5.61s | 一致(命中) |
| TP-07 | 28.93s | 28.88s | 一致(load 命中 + save 原生) |
| TP-08 | 61.01s | 61.97s | 一致(重算输出指纹跨任务不重复, 仍 MISS ×2) |
| TP-09/10 | 5.55/6.62s | 5.57/5.72s | 一致(命中) |
| TP-13 | 8.80s | 8.75s | 一致(命中) |
| TP-14 | 5.48s | 5.31s | 一致(命中) |

(其余零头调用两组一致,略。)

#### 单点微基准(12.3MB 压缩 / 250 万格工作簿; 容器内单命令手测, 历史窗口, 非本节 A/B 同窗)

| 操作 | stock | 组合 |
|------|----:|----:|
| 全量冷加载(MISS) | 22.3s | 21.0s(加速解析+落盘) |
| 重复加载(HIT) | 22.3s | **3.9s(快照重建)** |
| LibreOffice 重算形态(MISS/HIT) | 16.2s | 17.4s / **4.1s** |

#### 剩余瓶颈(下一步方向)

| 项 | 耗时 | 性质 |
|----|----:|------|
| TP-08 LibreOffice 重算 | ~16s | 负载本身(soffice 读入 12.3MB+重算+写出) |
| TP-07 存盘写路径 | ~25s | 250 万格逐格 Python 序列化, 两层均未覆盖(writer 侧融合是下一步) |
| 重算后文件首次双读 | ~11s(加速后) | 内容变更必然 MISS; HIT 已到 4s |
| 每格 C-API 硬成本 | ~7s/次 | Cell 分配/槽位/拷贝; 地板 = iterparse 7.6s |
