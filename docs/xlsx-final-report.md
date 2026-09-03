# XLSX 最终报告

## 一、调用链

### 1.1 外层框架说明

外层(`run_benchmark` / `RoundRobinTaskManager` / `DocumentRoundRunner` / `StatsCollector` / 配方加载等)只是 ​**bench-core 的框架外壳**​——一个模拟 agent 按固定剧本回放工具调用、外加评测仪表,用于造可复现负载。​**无需关心它的时间**​,真 agent 接进来这层会整体替换。本报告只聚焦里面真实 agent 会走的 ​**15 次工具调用**​。

> 前置(外壳做的,不计入 15):`prepare_workspace` 把种子 `cp -a /opt/document-bench/xlsx → <WS>` 并建 `output/`,使每次任务起点一致。
> `<WS>` = `/root/.openclaw/workspace/tool-modeling/SUB-MEM-OFFICE-01`(容器内工作区)。

### 1.2 15次工具调用

#### P01 inspect_prepare — 检查与准备

| # | 函数 | 执行命令                                                                                                                                       | 做什么                                         |
| --- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------ |
| 1 | read | `test -f /SKILL.md && head -c 65536 /SKILL.md >/dev/null`                                                                                  | `test` xlsx SKILL.md                   |
| 2 | exec | `cat /input/verify_xlsx_enhanced.py`                                                                                                       | `cat`校验脚本源码                          |
| 3 | exec | `cp /input/monthly_operations_template.xlsx /output/monthly_operations_report.xlsx`                                                        | `cp`模板→工作副本                         |
| 4 | exec | `cd && python3 -c "from openpyxl import load_workbook; wb=load_workbook('input/...template.xlsx', data_only=False); print('Sheets: ...')"` | `openpyxl` load 检查结构 |
| 5 | exec | `cd && python3 <<'PYEOF' …openpyxl 注入 BarChart/LineChart/PieChart…`                                                                    | `openpyxl` load 加载图表      |

#### P02 build — 增强

| # | 函数  | 执行命令                                                                                                                        | 做什么                                                        |
| --- | ------- | --------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| 6 | write | `mkdir -p `+ base64 heredoc 写`enhance_workbook.py`(10KB)                                                               | `write` 写py脚本            |
| 7 | exec  | `cd && python3 /opt/document-bench/bin/run_xlsx_helper_atomic.py enhance_workbook.py output/monthly_operations_report.xlsx` | `openpyxl` load + save |

#### P03 process_publish — 重算与导出(最重)

| #  | 函数 | 执行命令                                                                                                                                                                     | 做什么                                                         |
| ---- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------- |
| 8  | exec | `cd && python3 /root/.openclaw/skills/xlsx/scripts/recalc.py output/monthly_operations_report.xlsx 180 > output/formula_recalc.json`                                     | `openpyxl` load * 2 +计算   |
| 9  | exec | `cd && python3 -c "openpyxl.load_workbook('...report.xlsx', data_only=False)…"`                                                                                         | `openpyxl` load_workbook(data_only=False)读公式             |
| 10 | exec | `cd && python3 -c "openpyxl.load_workbook('...report.xlsx', data_only=True)…"`                                                                                          | `openpyxl` load_workbook(data_only=True)读计算值            |
| 11 | exec | `cat /output/formula_recalc.json`                                                                                                                                        | `cat`重算结果 JSON                                         |
| 12 | exec | `cd && python3 /opt/document-bench/bin/export_xlsx_csv.py output/monthly_operations_report.xlsx output/monthly_operations_summary.csv output/reconciliation_summary.csv` | `python`导出 Executive + Reconciliation 两 CSV |

#### P04 verify_deliver — 校验与交付

| #  | 函数 | 执行命令                                                                                                                                                                                                                                                                   | 做什么                                                    |
| ---- | ------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| 13 | exec | `cd && python3 input/verify_xlsx_enhanced.py output/monthly_operations_report.xlsx output/formula_recalc.json output/business_verification.json`                                                                                                                       | `openpyxl` load, 业务校验出 verification.json |
| 14 | exec | `cd && python3 /opt/document-bench/bin/write_xlsx_summary.py output/monthly_operations_report.xlsx output/business_verification.json output/formula_recalc.json output/execution_summary.json output/monthly_operations_summary.csv output/reconciliation_summary.csv` | `openpyxl` load, 汇总特征/sha256→JSON          |
| 15 | exec | `cd && test -s output/monthly_operations_report.xlsx && test -s output/monthly_operations_summary.csv && test -s output/reconciliation_summary.csv`                                                                                                                    | `test`断言交付物非空                               |

## 二、测试点说明

测试点 = 上面工具调用链路里的 15 次调用,每次调用即一个测试点。外层框架不计。

## 三、各阶段耗时

> 以下数据跑在蓝区的920b服务器

### e2e耗时

#### 15 个测试点实测

| TP    | 阶段                  | 函数    |     耗时 |    占比 | 操作描述                                          |
| ----- | ------------------- | ----- | -----: | ----: | --------------------------------------------- |
| TP-01 | P01 inspect_prepare | read  | 0.052s |  0.0% | `test` xlsx SKILL.md                          |
| TP-02 | P01 inspect_prepare | exec  | 0.052s |  0.0% | `cat` 校验脚本源码                                  |
| TP-03 | P01 inspect_prepare | exec  | 0.054s |  0.0% | `cp` 模板→工作副本                                  |
| TP-04 | P01 inspect_prepare | exec  |  29.7s | 11.5% | `openpyxl` load 检查结构                          |
| TP-05 | P01 inspect_prepare | exec  |  25.6s | 10.0% | `openpyxl` 加载图表                   |
| TP-06 | P02 build           | write |  0.16s |  0.1% | `write` 写 py 脚本                               |
| TP-07 | P02 build           | exec  |  51.0s | 19.8% | `openpyxl` load + save                        |
| TP-08 | P03 process_publish | exec  |  62.6s | 24.3% | `openpyxl` load × 2 + 计算                      |
| TP-09 | P03 process_publish | exec  |  20.9s |  8.1% | `openpyxl` load_workbook(data_only=False) 读公式 |
| TP-10 | P03 process_publish | exec  |  20.5s |  8.0% | `openpyxl` load_workbook(data_only=True) 读计算值 |
| TP-11 | P03 process_publish | exec  | 0.094s |  0.0% | `cat` 重算结果 JSON                               |
| TP-12 | P03 process_publish | exec  |   1.7s |  0.7% | `python` 导出 Executive + Reconciliation 两个 CSV |
| TP-13 | P04 verify_deliver  | exec  |  24.5s |  9.5% | `openpyxl` load, 业务校验出 verification.json          |
| TP-14 | P04 verify_deliver  | exec  |  20.6s |  8.0% | `openpyxl` load, 汇总特征/sha256→JSON      |
| TP-15 | P04 verify_deliver  | exec  | 0.078s |  0.0% | `test` 断言交付物非空                                |

#### 阶段小计

| 阶段 | 耗时 | 占比 |
|------|-----:|-----:|
| P01 inspect_prepare | 55.5s | 22% |
| P02 build | 51.1s | 20% |
| P03 process_publish | 105.8s | 41% |
| P04 verify_deliver | 45.1s | 17% |
| **总计** | **257.5s** | 100% |

### openpyxl热点分析

> 被测命令:`venv/bin/python -c "from openpyxl import load_workbook; wb=load_workbook('/tmp/xlsx_template.xlsx', read_only=False); wb.close()"`,分别套 `perf stat`/`perf record -F 997 -g`/`strace -c -f`。
> 数据集:跑的是**种子模板**(从镜像提取到宿主 `/tmp`),代表 TP-04 的全量 load;TP-09/10 读的是重算后的 report.xlsx(同 2.96M 行量级,文件结构略异)。

#### perf stat

| 指标 | 值(访问数 / miss 数) | 比率 | 解读 |
|------|------|------|------|
| cycles | 76.05B | — | — |
| instructions | 190.42B | **IPC 2.50** | >1,无 stall,吞吐正常 |
| cache-references / misses | 74.5B / 1.31B | **1.76%** | 低,cache 健康 |
| branch-instructions / misses | 37.04B / 262M | **0.71%** | 低,分支预测好 |
| L1-dcache loads / misses | 74.1B / 1.30B | **1.76%** | 低 |
| L1-icache loads / misses | 27.6B / 1.59B | **5.75%** | 中(最高,指令 cache) |
| dTLB loads / misses | 83.5B / 2.69B | **3.22%** | 中 |
| iTLB loads / misses | 27.8B / 87.6M | **0.32%** | 低 |

**结论:无微架构瓶颈。** IPC 2.50、各类 miss 率全低。user(26.18s)≈ elapsed(26.74s)→ 单线程打满一个核。24s 不是 cache/branch/TLB stall 造成,而是**指令总量巨大**(190B 条给 2.96M 行 → ~64K 指令/行)= 纯 Python 逐 Cell 物化的解释器开销。

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

1. 读 XML(stdlib expat + ElementTree):~14s,把 XML 字节变成 Element 树。
2. 建对象(openpyxl):~25s,把 Element 树变成 2.5M 个 Cell 对象。

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

**结论:99.93% 是 user CPU,syscall 只占 0.07%。** read 0.36ms(I/O 几乎为零,12MB 压缩 xlsx 一次读入,123.5MB 解压在进程内 CPU)。对象分配走 pymalloc 内存池不每对象 mmap,故 mmap/munmap 都是 arena 级、次数少。→ 非 I/O、非 syscall,纯 user CPU,strace 对这场景信号极少,真信号在 perf。

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

关键结构: **同一份 123.5MB / 12.3 万行 / 250 万格工作簿被完整解析 9 次**, 每次都是
独立 `python3` 进程(`docker exec`), 内存对象树用完即弃, 跨调用零复用。
9 × ~19s = 全流程的大头。

#### openpyxl 占 E2E 耗时

E2E 总计 257.5s, 其中 openpyxl(全量加载 ×9 + TP-07 的 save, 含 TP-08 内部的 2 次加载):

| 项 | 耗时 | 占 E2E |
|----|----:|----:|
| 全量加载 ×9(单次 ~19-30s) | 192.7s | 74.8% |
| TP-07 内 save(250 万格逐格序列化) | ~25s | ~9.7% |
| **openpyxl 合计** | **~218s** | **~84.6%** |

其余: LibreOffice 重算(soffice 本体) ~16s(6.2%), 杂项 I/O ~2.2s(0.9%), 流式读 ~1.7s。

## 四、优化点尝试

### 4.1 多次读取相同内容 -> 构建xml缓存

> 报告地址：https://wiki.huawei.com/domains/101868/wiki/272348/WIKI2026082712490869

#### 背景

XLSX 文档基准(2核4G 容器, 单任务)优化前端到端 **257.5s**。对全部 recipe 命令与冻结脚本逐一盘点后, 瓶颈高度集中: **同一份 123.5MB / 12.3 万行 / 250 万格的工作簿被完整解析了 9 次**(全量 `load_workbook` ×9), 每次都是独立 `python3` 进程, 内存对象树用完即弃、跨调用零复用。9 次加载合计 ≈ 193s, 占整个端到端的 **74.8%**; 算上唯一的存盘(TP-07, 250 万格逐格序列化 ≈ 25s), openpyxl 合计占 **≈84.6%**。其余是 LibreOffice 重算 ~16s(负载本身)与杂项 I/O ~2s。

也就是说: 这个流程最大的开销不是"算", 而是同一份数据被反复"读进来建对象、用一下、扔掉"。

#### 方案

##### 思路:跳过重复的 XML 解析

openpyxl 把一个 .xlsx 读进内存,大致分两段:

1. **XML 解析段(~14s)**:把文件里的 XML 读成内部结构,逐个单元格抽出值/类型/样式。
2. **单元格构造段(~3-5s)**:把这些数据组装成 2.5M 个单元格对象,放进工作表。

同一个文件被加载多次时,只有第一次需要解析;后续完全可以把第一次的结果存下来复用——**跳过第①段(14s),只保留第②段(造对象,无法再省,因为 2.5M 个对象必须造)**。这就是缓存的全部意义。

#### 最终数据

##### 端到端(同日同窗口 A/B, fixed 单任务)

| 指标 | 优化前 | 仅加缓存 | Δ |
|------|----:|----:|----:|
| Avg Latency | 257.5~258.7s | **165.5s** | **-36.0%** |
| Success Rate | 100% | 100% | — |

##### 逐调用(重复加载的 6 次全部命中)

| 调用 | 优化前 | 缓存后 | 机制 |
|------|----:|----:|------|
| TP-04 结构检查 | 29.7s | 33.3s | 首次 MISS: 正常解析 + 落盘(多出的 ~3s 是填充成本, 一次性) |
| TP-05 图表检查 | 25.6s | **5.4s** | 模板副本与 TP-04 同内容 → 指纹直接命中 |
| TP-07 增强存盘 | 51.0s | **29.2s** | load 侧命中; save 走原生路径不变 |
| TP-08 重算+双读 | 62.6s | 69.8s | 重算后是新文件, 两次加载必然 MISS(各付 ~3s 填充); soffice 部分不变 |
| TP-09 读公式 | 20.9s | **5.5s** | TP-08 落的盘, 命中 |
| TP-10 读值 | 20.5s | **5.5s** | 同上(另一视角的条目) |
| TP-13 业务校验 | 24.5s | **8.8s** | 命中 |
| TP-14 汇总特征 | 20.6s | **5.3s** | 命中 |

### 4.2 openpyxl speedups 扩展

> https://wiki.huawei.com/domains/101868/wiki/272348/WIKI2026083112558138

#### 背景: 钱花在哪

PMU 画像(此前已采集): 处理约 250 万 Cell 执行了 **~190B 条指令**, IPC 2.5, libpython 占 87%, libexpat 仅 6.5%, 无 memory stall、无 syscall 瓶颈。结论: 瓶颈不是"指令跑得慢", 是**每个单元格都在支付一套 Python 协议税**(对象分配/方法分发/中间 dict/字典查找)。

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

这些在 CPython 里全是解释器字节码: 对象分配、引用计数、方法分发、dict hash。250 万格 × 每格几十次解释器操作 = 190B 指令的主体。地板测量也印证: 纯 expat+Element 创建只要 7.6s, 冷加载却要 25s——多出的 ~17s 全是 Element→Cell 这一圈的 Python 协议税。

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

**语义等价(不是简化, 是搬运)。** 融合循环逐行复刻 openpyxl 3.1.5 的行为: date 格式的数值转换、共享字符串查找、inlineStr、公式判断、行维度副作用……全部调用 openpyxl 自己的同一批辅助函数。产物是原汁原味的 `openpyxl.cell.Cell`(`type(ws["A1"]) is Cell`)。

#### 实测

##### 端到端(同日同窗口 A/B, fixed 单任务)

| 指标 | stock | speedups | Δ |
|------|----:|----:|----:|
| Avg Latency | 258.3s | **217.9s** | **-15.4%** |
| Success Rate | 100% | 100% | — |

逐调用(对照此前的 stock 计时):

| 调用 | 内容 | stock | speedups | 降幅 |
|------|------|----:|----:|----:|
| TP-04 | 结构检查(冷加载) | 29.5s | 24.2s | -18% |
| TP-05 | 图表检查(冷加载) | 25.3s | 19.8s | -22% |
| TP-07 | 增强存盘 | 51.3s | 45.8s | -11% |
| TP-08 | 重算+双读 | 62.7s | 54.6s | -13% |
| TP-09/10 | 读公式/读值 | 20.9/20.5s | 16.9/16.9s | -19% |
| TP-13 | 业务校验 | 24.6s | 20.7s | -16% |
| TP-14 | 汇总特征 | 20.5s | 16.5s | -19% |

含 LibreOffice 的 TP-08 降幅来自该步骤中 soffice 前后的 openpyxl Python 处理; 存盘重的 TP-07 降幅里 load 侧贡献为主, save 侧走 stock 路径不变。

### 4.3 两个优化点结合(最终形态)

> 两层完全正交: 缓存救"重复解析"(9 次加载里 6 次纯重复, 命中后不碰 XML), speedups 救"每次解析的成本"(MISS 的 3 次冷解析走 C 融合循环)。镜像里同时注入两层共 5 个文件(注入钩子已处理多 .pth 共存的导入顺序竞争: openpyxl 被任一钩子先导入, 另一钩子立即补 patch)。

#### 实测(同日同窗口 A/B, fixed 单任务)

| 指标 | stock | 仅缓存 | 仅 speedups | **组合(最终形态)** |
|------|----:|----:|----:|----:|
| Avg Latency | 257.9s | 165.5s | 217.9s | **144.4s** |
| 相对 stock | — | -35.8% | -15.5% | **-44.0%** |
| Success Rate | 100% | 100% | 100% | 100% |

组合收益 113.5s = 6 次命中加载省 ~100s(缓存) + 3 次冷解析省 ~7s(speedups) + 命中重建自身也被加速。整体是"分工叠加": 命中的 6 次加载吃缓存重建(~4s 级), 未命中的 3 次冷解析吃 speedups 加速(~-25%), save 走原生路径两层都不碰。

#### 逐调用(对照 stock)

| 调用 | 内容 | stock | 组合 | 机制 |
|------|------|----:|----:|------|
| TP-04 | 结构检查 | 29.7s | 29.0s | 首次 MISS: 加速解析 + 落盘(一次性填充 ~3s) |
| TP-05 | 图表检查 | 25.6s | **5.4s** | 同内容指纹命中(模板副本), 快照重建 |
| TP-06 | 写增强脚本 | 0.16s | 0.30s | — |
| TP-07 | 增强存盘 | 51.0s | **30.1s** | load 侧命中; save 原生路径不变 |
| TP-08 | 重算+双读 | 62.6s | 63.7s | 重算后新文件两次 MISS(soffice ~16s 不变, 两次加速解析+填充) |
| TP-09 | 读公式 | 20.9s | **5.6s** | TP-08 落盘后命中 |
| TP-10 | 读值 | 20.5s | **5.5s** | 同上(另一视角条目) |
| TP-11 | 读重算 JSON | 0.09s | 0.09s | — |
| TP-12 | 导出 CSV | 1.7s | 1.7s | read_only 流式, 两层都不碰 |
| TP-13 | 业务校验 | 24.5s | **8.7s** | 命中重建 |
| TP-14 | 汇总特征 | 20.6s | **5.5s** | 命中重建 |
| TP-15 | 断言交付 | 0.08s | 0.21s | — |

#### 单点微基准(123.5MB / 250 万格工作簿)

| 操作 | stock | 组合 |
|------|----:|----:|
| 全量冷加载(MISS) | 22.3s | 21.0s(加速解析+落盘) |
| 重复加载(HIT) | 22.3s | **3.9s(快照重建)** |
| LibreOffice 重算形态(MISS/HIT) | 16.2s | 17.4s / **4.1s** |

#### 剩余瓶颈(下一步方向)

| 项 | 耗时 | 性质 |
|----|----:|------|
| TP-08 LibreOffice 重算 | ~16s | 负载本身(soffice 读入 123MB+重算+写出) |
| TP-07 存盘写路径 | ~25s | 250 万格逐格 Python 序列化, 两层均未覆盖(writer 侧融合是下一步) |
| 重算后文件首次双读 | ~11s(加速后) | 内容变更必然 MISS; HIT 已到 4s |
| 每格 C-API 硬成本 | ~7s/次 | Cell 分配/槽位/拷贝; 地板 = iterparse 7.6s |
