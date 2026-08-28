# XLSX openpyxl 全量加载 profiling 报告

> 仿 `~/yxy/grep-bench/scripts/perf-rg.sh` 三段式,单测一个代表性重操作(openpyxl 全量 load,~24s,XLSX 主成本),非端到端。
> 被测命令:`venv/bin/python -c "from openpyxl import load_workbook; wb=load_workbook('/tmp/xlsx_template.xlsx', read_only=False); wb.close()"`,分别套 `perf stat`/`perf record -F 997 -g`/`strace -c -f`。
> 数据集:跑的是**种子模板**(从镜像提取到宿主 `/tmp`),代表 TP-04 的全量 load;TP-09/10 读的是重算后的 report.xlsx(同 2.96M 行量级,文件结构略异)。
> 不端到端的原因:15 次调用是各自独立的容器内进程(python3/soffice),宿主 perf 测 `bench-core` 只看到 docker exec RPC 等待、测不到真业务;且调用异构(纯 Python + 原生 C++ + IO)混跑难归因。单测一个重操作信号干净。
> **本报告数据取自干净 venv(仅装 openpyxl,无 numpy/pandas)→ 无 openblas 噪声,为权威值**。首轮(宿主 venv 含 numpy)有 openblas 噪声,见末尾"噪声对照"。

## perf stat(PMU,单次,26.74s elapsed / 26.18s user / 0.46s sys)

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

## perf record 热点(Top,-F 997,call-graph dwarf,26K 样本)

| Overhead | 符号 | 解读 |
|----------|------|------|
| **15.83%** | `_PyEval_EvalFrameDefault`(libpython3.11) | ✅ CPython 字节码主循环,真业务主体 |
| 3.60% | `PyObject_Malloc` | 对象堆分配(Cell 物化) |
| 1.81% | `_PyType_Lookup` | 属性类型查找 |
| 1.43% | `_PyObject_GenericGetAttrWithDict` | 属性取 |
| 0.87% | `PyObject_GC_Del` | GC 回收对象 |
| 0.79% | `PyObject_GetAttr` | 属性取 |
| 0.45% | `PyLong_FromString` | 数字串转 long(每 Cell 值) |
| 0.41% | `PyObject_IsTrue` | 真值判断 |
| 0.38% | `_Py_HashBytes` | Cell 样式 dict hash |
| 0.37% | `PyDict_SetItem` | Cell 样式 dict |
| ~1.9% | `libexpat`(1.05%+0.50%)+ `_elementtree`(0.37%) | XML 解析,占比小 |

> ⚠️ **修正**:这是**符号视图**,expat 符号被 strip/inline,只归因了命名部分。`perf report --sort dso` 的 DSO 视图才是准确值:libexpat **6.54%** + _elementtree 3.57%(XML 栈实占 ~10%,非 1.9%)。用 LD_PRELOAD 自建带符号 expat 2.8.3 验证:libexpat 6.10%,命名热点 doContent 0.74% + poolStoreString 0.14%,其余 ~5% 在内联碎片。
| 0.53% | `__memcpy_generic`(libc) | 内存拷贝 |

**结论:热点 = CPython 解释器(建对象/属性/dict 运算)+ XML 解析,两段都实在。** `_PyEval_EvalFrameDefault` 15.83% + `PyObject_Malloc` + `_PyType_Lookup` + GetAttr/SetItem/Hash 一族是建对象的开销;XML 解析**不是小头**——cProfile 里 expat `feed` 是 #1 热点(8.92s),加 ElementTree 遍历 ~5s,stdlib 段 ~14s(占 ~36%);openpyxl 建对象段 ~25s(占 ~64%,更大头)。**load 慢 = 读 XML + 建 2.5M 个 Cell 对象 两圈活**,不是"读 XML 可忽略"。(注:perf 符号视图的 1.9% 是 strip/inline 导致的低估,见上文 DSO 修正 6.54%+3.57%。)

## strace -c -f(系统调用)

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

## 噪声对照(为何用干净 venv)

首轮在宿主 venv(`pip install -e .` 带 pandas→numpy)跑时,`import openpyxl` 触发 `openpyxl/compat/numbers.py` 的 `try: import numpy`(可选依赖,为支持 numpy 数值类型作 cell 值)→ numpy 加载 → dlopen BLAS 后端 → openblas 起后台线程 `blas_thread_server` 空转,污染 profiling:

| | 含 numpy(噪声) | 干净 venv(无 numpy) |
|---|---|---|
| cycles | 90.96B | **76.05B**(−16%) |
| IPC | 2.14 | **2.50** |
| user time | 31.4s(>elapsed,多线程) | **26.18s ≈ elapsed**(单线程) |
| 热点 #1 | `blas_thread_server` 16.72%(噪声) | `_PyEval_EvalFrameDefault` 15.83%(真业务) |
| strace #1 | futex 99.89%(30s,噪声) | munmap 90.97%(0.018s);futex 0% |
| load 时间 | 24.12s | 23.73s(不变 → 噪声没拖慢 load,只污染 perf 数据) |

> 根因:`openpyxl/compat/numbers.py` 在 import 时 `try: import numpy`。宿主 venv 装了 numpy → 触发;干净 venv(或容器镜像若不装 numpy)→ try 失败、`NUMPY=False`、无 openblas。`OPENBLAS_NUM_THREADS=1` 只抑线程池、不阻 import;要彻底消除需无 numpy 环境。

## 综合结论

| 维度 | 结论 |
|------|------|
| 微架构(PMU) | 无瓶颈(IPC 2.50,miss 率全低,user≈elapsed 单线程)——非 cache/TLB/branch stall |
| 热点函数 | CPython 解释器(建对象/属性/dict)+ XML 解析;两段都实在(建对象 ~64%、读 XML ~36%) |
| I/O(strace) | 非 I/O bound(read 0.36ms),123.5MB 进程内解压,纯 CPU bound |
| 根因 | **纯 Python 逐 Cell 物化开销巨大(190B 指令),非微架构/非 I/O** |

**对优化的指向**:既非硬件 stall 也非 I/O,PMU/strace 层面无杠杆;瓶颈在"用纯 Python 物化 2.96M 个 Cell 对象"本身。已验证的杠杆:
1. ✅ **缓存(cell-less pickle + 手动重建 Cell)**——命中 4.6s vs 冷 24s,md5 bit-for-bit 一致,基准收益 ~11–21%。目前最大杠杆。详见下文"缓存方案"。
2. ❌ read_only(原 #1,−13.6%)——违反"recipe 冻结"约束,已回滚。
3. 架构级(产品线):换 Rust 后端 `python-calamine`(C/原生解析,绕开 CPython 逐对象开销)。

## Kunpeng 920 角度(实测,低 ROI)

CPU:HiSilicon Kunpeng(2 socket × 80 核 = 160 CPU,4 NUMA,L1d/L1i 64K、L2 1.3M、L3 70M×4,2.9GHz,SVE)。`governor=performance`、`THP=always`(环境已最优)。

4 组对照(同一 openpyxl 全量 load):
| 配置 | 耗时 | vs 基线 |
|------|-----:|-------:|
| 基线 | 24.12s | — |
| + OPENBLAS_NUM_THREADS=1 | 23.9s | −0.9%(噪声) |
| + numactl 绑 node0 | 23.59s | −2.2%(噪声) |
| 两者都加 | 23.92s | −0.8%(噪声) |

**结论:Kunpeng 角度无实质收益(±2% 噪声)。** 原因:PMU 已示无 hw stall(IPC 2.50、miss 全低),NUMA/缓存/核绑定无处着力;env(governor/THP)已最优;openblas 线程在 160 核上占空闲核不抢主线程。瓶颈是纯 Python 指令量(190B),非 CPU 微架构——故优化杠杆仍是 read_only(已做)/calamine(原生 reader),与具体 CPU 无关。

---

## cProfile 热点函数(纯 Python 层,perf record 看不到的)

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
| 16 | `parse_row <listcomp>` | 0.70 | 100K | openpyxl/_reader.py:303 |
| 17 | `base.__set__` | 0.68 | 3.2M | openpyxl/descriptors/base.py:24 |
| 18 | `localname` | 0.65 | 801K | openpyxl/xml/functions.py:77 |
| 19 | `Element.find` | 0.64 | 3.3M | xml.etree.ElementTree |
| 20 | `nested.__set__` | 0.63 | 801K | openpyxl/descriptors/nested.py:26 |

**关于 49.663s**:cProfile 报的总量 = **所有函数 tottime 之和**,内含 profiler 对 **89M 次函数调用**的埋点开销本身(每次调用 profiler 记一笔,~0.3µs × 89M ≈ 25s 摊进各函数的 tottime)。故真实 wall 才 ~24s,cProfile 虚高约 2×。上表 top 20 合计 ~40s,余 ~9s 在更小的尾(`base.__get__`/`_cast_number`/`re.match`/`findtext`/`popleft`/`zipfile.read`/`getattr`/`child.parent`/`parse_row` …)。**绝对秒数不可信(含埋点税),只有相对排名可信**。算收益一律用 wall time。

**两堆(按可改性):**
- **openpyxl 可改**(2/3/4/6/7/8/9/11/12/16/17/18/20 …)= ~25s+ —— 主战场在 **per-cell ×2.5M**:`parse_cell`+`coordinate`+`Cell.__init__`+`styleable`+`sequence/nested/base __set__`(描述符赋值)+ `from_tree`(反射);外加 `bind_cells`/`parse` 分派器。
- **stdlib 不可改**(1/5/13/14/19 …)= ~16s —— expat 逐字符 `feed`(8.92)+ iterparse `read_events`/`iterator`/`Element.get`/`find`。
- 第 10 `isinstance`(13M 次)和 `__new__` 是 Python 内建,夹在两堆之间。

> 这是 perf record 的补充:perf 看 native DSO(libpython 87% / expat 6.54% / _elementtree 3.57%),cProfile 看 Python 函数名,两层拼起来才完整。cProfile 的价值是点名 per-cell 热路径(parse_cell→coordinate→Cell.__init__→styleable→descriptor __set__),perf 的价值是确认大头在 libpython 解释器分派而非 cache/TLB stall。

### cProfile 结论

> 注:cProfile 埋点有自身开销,绝对秒数虚高,看相对占比。

1. **读 XML(stdlib expat + ElementTree):~14s,把 XML 字节变成 Element 树。**
2. **建对象(openpyxl):~25s,把 Element 树变成 2.5M 个 Cell 对象。**

建对象是大头,读 XML 也不小。成本摊在十几个函数上无单点,所以改单个函数(如 OP1)收益小。

## SVE 优化 expat:排除(架构不匹配)

用带符号 expat 2.8.3 + LD_PRELOAD 拿到 expat 命名热点:`doContent` 0.74%(内容状态机)、`poolStoreString` 0.14%、`poolAppend` 0.05%,其余 ~5% 在编译器内联进状态机的碎片。

**结论:expat 周期散布在 char-by-char 状态机的内联碎片里,无单一可向量化的扫描循环。** SVE 要"连续数据 + 无数据依赖的批量同构操作";expat 每字符条件分支的状态机无法向量化。对比 SIMD 友好的 simdjson(单一 30%+ 批量扫描函数),expat 完全相反。**SVE 进不去 expat**;真要 SIMD-XML 得换为 SIMD-designed 解析器(软件层,产品线)。

## lxml 替代 stdlib:证伪(更慢)

openpyxl 3.1.5 有 lxml 代码路径(`LXML=True` 时 `functions.py` 用 `lxml.etree`),但 `iterparse` **无条件走 stdlib**(`functions.py:40` `from xml.etree.ElementTree import iterparse`,在 `if LXML` 块外)。调用方 `worksheet/_reader.py` 和 `reader/strings.py` 都 `from openpyxl.xml.functions import iterparse`(绑本地名),所以要 patch 三个点:`openpyxl.xml.functions` + `openpyxl.worksheet._reader` + `openpyxl.reader.strings`。patch 确认生效(三次各跑):

| | wall(min) | mean | md5 |
|---|---:|---:|:---:|
| stdlib `ElementTree.iterparse` | 25.78s | 25.89s | `895bf0c5dd3c` |
| lxml `etree.iterparse` | **40.81s** | 41.13s | `895bf0c5dd3c` |

md5 完全一致(忠实),但 **lxml 在 zip 流 + 2.5M 元素上比 stdlib 慢 ~59%**(+15s)。lxml 的 Element 是 C xmlNode + Python proxy,比 stdlib 的轻量 Python Element 更重;2.5M 个更重的对象,内存 + GC 更累;zip 流喂 libxml2 iterparse 也多一层缓冲。**stdlib 读 XML 这圈砍不动,lxml 是死路。**

## 多线程 / GIL:排除

openpyxl load 87% 是 CPython 解释器分派字节码(`parse_cell`/`bind_cells`/`Cell` 构造 ~13s 全 Python),GIL 保证同一时刻只有一个线程跑 Python 字节码 → 多线程零加速。唯一能释放 GIL 的是 expat C 解析,理论可做 producer-consumer 重叠,但 Cell 构造(~13s)比 expat(~8.9s)重且是 GIL 持有的瓶颈,流水线上限 ~30% 且要重构。真用第 2 核只能多进程(重 + 跨进程序列化税),且 recipe 串行挡了跨调用并行。**2核4G 容器下线程/多进程非有效杠杆。**

## NUMA 绑核:修正(消尾延迟,非提峰)

上文"±2% 噪声"不完整。实测(各 3 次):
- default:**26.5–30.3s**(抖,偶尔落远端节点慢 14%)
- NUMA0 绑核:**26.1–26.6s**(稳)

即绑核**峰值不变(都是 ~26.4s)**,只是消"偶尔 30s 的尾"。对求可复现的基准有意义,对吞吐几乎没用。容器内 `--cpus=2` 限配额但不钉 NUMA,2 核配额跨节点漂;加 `--cpuset-cpus`/`--cpuset-mems` 能消尾但要改 docker provider。

## OP1(dict→tuple):实现测过,因约束回滚

`parse_cell` 返回 dict、`bind_cells` 按 key 读 → 改 tuple 位置解包(省 2.5M dict 分配 + 5M 哈希查)。实测 cProfile tottime:`parse_cell` 5.95→5.56、`bind_cells` 3.82→3.52(~0.7s CPU),md5 一致。但约束是"不直接改 openpyxl 源码"(保持 vendor pristine),已回滚 vendor 改动,改以缓存层(patch)方式做。

## 缓存方案(已验证,目前最大杠杆)

### 现象:同一文件被冷加载 7 次
TP-04/05/07/09/10/13/14 各自独立 python 进程(recipe 冻结,串行),同一 2.5M 工作簿冷加载。尤其 **TP-09/10/13/14 都 load 同一"重算后" report.xlsx(同 mtime)→ 4 次冷加载 ~86s**。

### 方案:cell-less pickle + 手动重建 Cell
全量 pickle wb 太重(dump 15.6s + blob 338MB)。改为:load 后清空 `_cells` 再 pickle wb(小:含全部非单元格结构 charts/dv/condfmt/merged/styles/shared_strings/external_links),命中时 unpickle 小 wb + 从抽出的 `(r,c,val,dt,style_id)` 元组手动重建 `_cells`。

实现:`patches/openpyxl_cache.py`(monkey-patch `load_workbook`,磁盘 blob,key=路径+mtime+size+data_only;save/recalc 改 mtime → 自动失效)+ `sitecustomize.py`(PYTHONPATH 自动加载,recipe 不动)。

### 实测(宿主 venv-clean)
| 项 | 值 |
|----|----|
| COLD(load 24s + 填缓存 4.8s) | 28.8s |
| **HIT(重建)** | **4.6s** |
| blob | 57.7MB |
| md5 | miss == hit == 基线 `312ee250…` ✓ bit-for-bit 忠实 |
| 结构完整 | miss + hit 都 ok(merged_cells / data_validations / freeze_panes / conditional_formatting / _external_links 全可访问)✓ |

### 命中路径新热点(cProfile)
冷路径 7 个热点里 5 个是 XML 解析段,HIT 全跳过。命中后塌缩成"造 2.5M 个 Cell":

| # | 函数 | tottime | vs 冷路径 |
|---|------|------:|------|
| 1 | `Cell.__init__` (cell.py:108) | 3.33s | 1.80→3.33(占比升,因别的没了) |
| 2 | `_rebuild_cells` 循环 (cache.py) | 2.99s | 新增(重建循环开销) |
| 3 | `StyleableObject.__init__` | 0.36s | **1.14→0.36(OP3 已实现:跳 StyleArray re-wrap)** |
| 4 | `_pickle.load` | 0.34s | 新增(反序列化 cell-less wb) |

**消失的**:expat feed(8.9)、parse_cell(5.95)、from_tree(2.45)、read_events(2.36)、coordinate(2.26)——全是 XML 解析段,缓存命中直接绕过。命中地板 = 2.5M Cell 对象构造(~3.3s)+ 重建循环(~3.0s),再砍只能 C 扩展或换不物化架构。

### 基准收益推算(2核4G 容器内 TP-09/10/13/14)
- **朴素缓存**(按 data_only 分桶):2 冷 + 2 命中 → 省 ~29s(全基准 ~11%)。
- **双模式缓存**(一次解析同时取 `<f>` 和 `<v>`,供 False/True 两模式):1 冷 + 3 命中 → 省 ~53s(~21%)。

### 现状与待办
- ✅ 宿主已验证(HIT 4.6s,md5 一致,结构完整)。
- ⚠️ 容器内 `sitecustomize.py` 自动加载**未通**(`site` 模块未在启动时调它,无条件 print 不出)——待修(可能需 `.pth` 文件或改 site-packages 路径)。
- 缓存镜像已 build:`ubuntu-document-bench:cached`(overlay FROM base + COPY 两文件到 `/usr/local/lib/python3.12/dist-packages/`)。
- `venv-clean` 装了 lxml 6.1.2(测 iterparse 用),可卸。
