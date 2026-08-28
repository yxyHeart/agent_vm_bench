# XLSX native 侧杠杆分析:NUMA / 多线程 / SVE

> 本文档记录三个 CPU/硬件底层方向的具体实测(命令 + 数据)与结论。被测负载统一为 openpyxl 全量 load(`/tmp/xlsx_template.xlsx`,2.96M 行 / 2.5M 单元格,`data_only=False`),在 j 服务器(Kunpeng 920)上跑。三个方向均**被排除或边际**,结论见各节末尾。

## 环境

- **CPU**:HiSilicon Kunpeng 920,2 socket × 80 核 = **160 CPU**,2.9 GHz,支持 SVE。
- **NUMA 拓扑**(`numactl -H`):

| node | cpus | size |
|------|------|------|
| 0 | 0–39 | 64378 MB |
| 1 | 40–79 | 63948 MB |
| 2 | 80–119 | 63472 MB |
| 3 | 120–159 | 64449 MB |

- **环境已最优**:`governor=performance`、`THP=always`。
- **venv**:`venv-clean`(仅装 openpyxl,无 numpy → 无 openblas 噪声),`/tmp/xlsx_template.xlsx` 为种子模板。

---

## 1. NUMA 绑核

### 怎么做的(具体命令)
用 `numactl` 把进程钉到 node 0 的 CPU + 本地内存,对照不绑(default,内核自由调度,可能跨节点漂):

```bash
# default(对照,不绑)
venv-clean/bin/python -c "from openpyxl import load_workbook; wb=load_workbook('/tmp/xlsx_template.xlsx',data_only=False); wb.close()"

# NUMA0 绑核(CPU + 内存都钉到 node 0)
numactl --cpunodebind=0 --membind=0 venv-clean/bin/python -c "from openpyxl import load_workbook; wb=load_workbook('/tmp/xlsx_template.xlsx',data_only=False); wb.close()"
```

- `--cpunodebind=0`:只允许在 node 0 的 40 个核(0–39)上调度。
- `--membind=0`:内存分配只在 node 0 的本地内存(避免跨节点远端访存)。
- 各跑 3 次,取 wall time。

### 数据(3 次/组)
| run | default | NUMA0 绑核 |
|----|--------:|----------:|
| 1 | 30.34s(cold) | 26.13s |
| 2 | 26.52s | 26.35s |
| 3 | 29.16s | 26.61s |
| **范围** | **26.5–30.3s(抖)** | **26.1–26.6s(稳)** |
| **中位** | ~29s | ~26.4s |

首轮(单次/组,旧数据,记录在 `xlsx-profiling-report.md`):基线 24.12s、`+numactl 绑 node0` 23.59s(−2.2%)、`+OPENBLAS_NUM_THREADS=1` 23.9s(−0.9%)、两者都加 23.92s(−0.8%)——单次噪声大,以 3 次/组为准。

### 结论
- **绑核峰值不变**(default 最好一次 26.52 ≈ NUMA0 中位 26.4)→ **不是真算力提升**。
- 绑核的价值是**消尾延迟**:default 偶尔落到远端 NUMA 节点(内存非本地)→ 慢到 30s(+14%);NUMA0 钉本地 → 始终 ~26.4s。
- **对吞吐无用,对求可复现的基准有意义**(削掉 30s 的尾)。
- **容器内不适用**:docker `--cpus=2.0` 只限 CPU 配额,**不钉 NUMA**,2 核配额仍跨节点漂;要消尾得给容器加 `--cpuset-cpus`/`--cpuset-mems`(改 docker provider)。
- **为何无实质收益**:PMU 已示无 hw stall(IPC 2.50、miss 全低),NUMA 远端访存的延迟差在"无 stall 的工作负载"上看不出峰值差异,只表现为偶尔的调度抖动。

---

## 2. 多线程

### 怎么做的
**未做运行时实测**——因为 GIL 使 Python 段 *a priori* 不可并行,无测的必要。结论由 profiling 数据推出:

### 数据支撑(来自 perf + cProfile)
- **perf DSO**:libpython3.11 **87%** = CPython 解释器分派 openpyxl 的字节码。
- **cProfile**:openpyxl 物化链(parse_cell 5.95 + bind_cells 3.82 + from_tree 2.45 + coordinate 2.26 + Cell.__init__ 1.80 + styleable 1.14 + descriptor __set__ 一族 …)= ~25s,全是 **Python 字节码**。
- 释放 GIL 的只有 expat C(`XMLParser.feed` 8.92s)和少量 `_elementtree` C 段。

### 分析
- **GIL**:CPython 全局解释器锁保证同一时刻只有一个线程执行 Python 字节码。openpyxl load 87% 是解释器分派 → **多线程跑这部分 = 零加速**,跟单线程一样。
- **唯一能重叠的**:expat C 解析(释放 GIL)可与 Cell 构造(持 GIL)做 producer-consumer 流水线。但:
  - Cell 构造(~13s,持 GIL)> expat(~8.9s,释放 GIL)→ **流水线瓶颈在持 GIL 的那段**。
  - 理论上限 ~30%(把 expat 的 8.9s 折叠掉),且需要重构 iterparse 为 producer-consumer + 队列 + element 生命周期管理,不是加 `threading.Thread`。
  - 还受 `_elementtree` 建 Element 时是否也释放 GIL 制约(不确定)。
- **多进程**:子进程各自 GIL,能真并行。但 `load_workbook` 返回**单个 workbook 对象**,要按 sheet/行段切到子进程,再把 2.5M Cell 跨进程序列化(pickle)回主进程——序列化开销可能吃掉收益,且是大改 API。
- **2核4G 容器**:只有 2 核,加不了;且 recipe 串行跑各 `python3 -c` 调用(冻结),跨调用并行也被挡。

### 结论
- **多线程排除**(GIL 把 87% 的 Python 段锁死,那是大头)。
- 唯一窗口是 expat C 重叠(不确定、要重构、上限 ~30%)。
- 真用第 2 核只能多进程(重 + 序列化税 + recipe 串行挡)。
- **2核4G 下线程/多进程非有效杠杆**。

---

## 3. SVE 优化 expat

### 怎么做的(具体步骤)
1. 下载 expat 2.8.3 源码,`cmake -DCMAKE_BUILD_TYPE=RelWithDebInfo` 带 symbols 编译,装到 `~/yxy/expat-dev/install/lib64/libexpat.so.1.12.3`。
2. `LD_PRELOAD` 我的带符号 expat,跑 openpyxl load + `perf record`,再 `perf report` 按 DSO 和符号看 expat 内部命名热点。

```bash
LIB=$HOME/yxy/expat-dev/install/lib64
# perf record with my expat
perf record -F 997 -o /tmp/expat_pre.data -- env LD_PRELOAD=$LIB/libexpat.so.1 \
  venv-clean/bin/python -c "from openpyxl import load_workbook; wb=load_workbook('/tmp/xlsx_template.xlsx',read_only=False); wb.close()"
# per-DSO
perf report -i /tmp/expat_pre.data --stdio --no-children -g none --sort dso
# expat 命名热点
perf report -i /tmp/expat_pre.data --stdio --no-children -g none --sort symbol | grep -iE "doContent|doProlog|poolStore|poolAppend|XML_Parse|Processor"
```

### 数据
**per-DSO**(LD_PRELOAD 我的 expat 生效,libexpat 从系统 1.8.10 换成 1.12.3):

| DSO | 占比 |
|-----|----:|
| libpython3.11.so.1.0 | 86.97% |
| **libexpat.so.1.12.3** | **6.10%** |
| _elementtree.cpython-311 | 3.60% |
| libc.so.6 | 2.31% |
| libz.so.1.2.13 | 0.70% |

**expat 命名热点**(带符号,终于能点名):

| 函数 | tottime |
|------|------:|
| `doContent`(内容状态机) | 0.74% |
| `poolStoreString`(字符串池存) | 0.14% |
| `poolAppend`(字符串池追加) | 0.05% |
| `callProcessor.constprop.0` | ~0% |
| `XML_Parse` / `XML_ParseBuffer` | ~0% |
| **其余 ~5.1% 在未命名的内联碎片** | — |

关键:命名函数合计才 ~0.93%,但 libexpat 总占 6.10% → **~5.1% 的周期在编译器内联进状态机的碎片里,无法点名**。

### 结论
- **expat 周期散布在 char-by-char 状态机的内联碎片里,无单一可向量化的扫描循环**:
  - top 命名函数 `doContent` 才 0.74%,其余 ~5% 全是内联碎片——没有"一个 30% 的批量扫描函数"的形态。
  - `doContent` 逐字符处理内容(字符引用、实体、CDATA 边界),每字符驱动**数据相关的状态转移 + 分支**。SVE 要"连续数据 + 无数据依赖的批量同构操作";expat 每字符条件分支的状态机**无法向量化**——不能把一串带分支的字符状态转移塞进一条 SVE 指令。
  - `poolStoreString`/`poolAppend` 倒有点 memcpy 性质(可向量化),但只 0.19%,忽略。
- **对比 SIMD 友好的 simdjson**:单一 30%+ 的批量扫描函数,expat 完全相反。
- **SVE 进不去 expat**;真要 SIMD-XML 得换为 SIMD-designed 解析器(branchless、bulk-scan)——那是**换库**(软件层,产品线),不是给 expat 打 SVE 补丁。
- expat 的 6.1% 是其标量 SAX 架构的固有开销,CPU 侧(含 SVE)消不掉。

---

## 三者汇总

| 方向 | 命令/方法 | 数据 | 结论 |
|------|----------|------|------|
| NUMA 绑核 | `numactl --cpunodebind=0 --membind=0` | 绑核 26.1–26.6s 稳 vs default 26.5–30.3s 抖 | **边际**(只消尾,不提峰) |
| 多线程 | (分析,无实测) | 87% libpython(GIL);expat C 仅 8.9s | **排除**(GIL 锁死 Python 段) |
| SVE 优化 expat | 自建带符号 expat 2.8.3 + LD_PRELOAD + perf | doContent 0.74% + 内联碎片 ~5%(散布) | **排除**(char-by-char 状态机,无向量化循环) |

**共同根因**:openpyxl load 是"CPython 解释器 bound 的单线程物化"工作负载——无 stall(PMU 已证)、单线程(GIL)、无向量化目标(expat char-by-char)。三个 CPU/硬件方向都无处着力,瓶颈在"用纯 Python 物化 2.5M Cell"本身,与具体 CPU 微架构无关。真正与根因对口的杠杆是**缓存**(命中跳过整条物化链),非 CPU/硬件侧。
