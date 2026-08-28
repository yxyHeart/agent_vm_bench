# XLSX 文档基准 openpyxl 加载缓存优化报告

> 日期: 2026-08-28 ｜ 场景: 2核4G docker 容器,XLSX 文档基准(document-xlsx),recipe 冻结
> 结论: 容器内验证通过,**单任务 259s → 174.9s,省 84s(-33%)**;业务校验 **100% 通过(逐单元格 bit-for-bit 一致)**

## 一、概要

优化不改 recipe(15 条工具调用一字不动)、不改容器规格(2核4G)、不改被测负载本身,仅在容器内**透明注入一个 openpyxl `load_workbook` 的磁盘缓存层**:重复加载同一工作簿时跳过 XML 解析,直接从缓存重建 2.5M 个单元格对象。注入通过镜像 overlay 的一个 `.pth` 文件,容器内每个 `python3` 启动即生效,recipe 命令完全无感。

## 二、背景:7 次冗余全量加载

15 次工具调用里有 **7 次 openpyxl 全量 `load_workbook`**(占总时长 ~75%),每次都把 123.5MB / 2.96M 行工作簿从零解析一遍:

| TP | 阶段 | 加载对象 | 基线 |
|----|------|----------|----:|
| 04 | P01 | 模板(查结构) | 29.7s |
| 05 | P01 | 模板副本(加图表) | 25.6s |
| 07 | P02 | 增强后件(改+存) | 51.0s |
| 09 | P03 | 重算后件(读公式) | 20.9s |
| 10 | P03 | 重算后件(读值) | 20.5s |
| 13 | P04 | 业务校验 | 24.5s |
| 14 | P04 | 汇总特征 | 20.6s |

存在大量可复用的重复解析:TP-09/10/13/14 加载同一份"重算后"文件;TP-04 与 TP-05 加载同内容不同路径(模板与其副本);TP-05 存盘后的版本被 TP-07 加载。

## 三、方案

### 3.1 思路:跳过重复的 XML 解析

openpyxl 把一个 .xlsx 读进内存,大致分两段:

1. **XML 解析段(~14s)**:把文件里的 XML 读成内部结构,逐个单元格抽出值/类型/样式。
2. **单元格构造段(~3-5s)**:把这些数据组装成 2.5M 个单元格对象,放进工作表。

同一个文件被加载多次时,只有第一次需要解析;后续完全可以把第一次的结果存下来复用——**跳过第①段(14s),只保留第②段(造对象,无法再省,因为 2.5M 个对象必须造)**。这就是缓存的全部意义。

### 3.2 缓存存什么

缓存文件(约 58MB)存两样东西:

- **工作簿的"壳子"**:把单元格全部清空后的工作簿——但**保留所有非单元格结构**:图表、数据有效性、条件格式、合并单元格、冻结窗格、外部链接、样式表、共享字符串表。这些是后续校验/汇总脚本要读的,必须完整。清空单元格后壳子很小、存取快。
- **单元格数据表**:每个单元格的坐标、值、数据类型、样式编号——一张紧凑的表(2.5M 行)。

绝大部分体积是 2.5M 个单元格的值。

### 3.3 首次加载(MISS):正常解析 + 顺手存快照

第一次加载某文件:照常把 .xlsx 解析成完整工作簿(**结果与未开缓存完全一致**),然后抽出单元格数据表、把壳子(无单元格的工作簿)存下来,再把单元格放回工作簿返回给调用者。存快照的过程不影响返回的工作簿;存失败也不影响(降级为未缓存)。

### 3.4 重复加载(HIT):跳过解析,从快照重建

再加载同一个文件:直接读快照,把壳子还原,按数据表把 2.5M 个单元格一个个造出来。跳过全部 XML 解析,只剩造对象——约 4.6s(宿主)/ ~6s(2核容器)。

### 3.5 缓存键:按文件内容,不按路径或时间

用文件首尾 4MB 的 md5 + 文件大小作为键(20ms 算完)。三点好处:

- **同内容不同路径共享**:模板和它的副本(被 cp 成另一个路径)内容相同、键相同,共享一份快照。
- **改写即失效**:存盘/重算重写文件后内容变 → 键变 → 自动重新解析,不会读到陈旧快照。
- **不依赖时间戳**:避免"同一秒内多次改写"导致键碰撞。

读公式和读值是同一文件的两种视角、产出不同的单元格值,分开存(各一把钥匙)。

### 3.6 存盘后也填缓存:让"存盘→再读"链命中

有个空子:有些文件是"读出来、改一改、存回去",下一个调用再读。但"存盘"这个动作不经过加载,所以存完的新文件没被解析过,下次读还是冷启动。

解决办法:**给存盘动作也加一层包装**——存盘成功后,顺手把内存里刚存下去的工作簿(就是新文件的内容)存成快照。这样下一个加载直接命中,无需重新解析。整条"存盘→再读"链逐级命中。

### 3.7 注入:对 recipe 透明

缓存逻辑放进镜像的一个 `.pth` 文件里。容器内每次启动 Python,系统自动加载它,把 openpyxl 的加载和存盘函数替换成带缓存的版本。recipe 的 `python3 -c "from openpyxl import load_workbook..."` 命令一个字不改,自动走缓存。

镜像只是在基础镜像上加一层、拷两个文件进去,秒级构建;用哪份配置文件决定开不开缓存:
```
FROM ubuntu-document-bench:24.04-linuxarm64
COPY openpyxl_cache.py oxlcache.pth /usr/local/lib/python3.12/dist-packages/
```

### 3.8 不缓存的情形

- **流式只读模式**:不把单元格全部载入内存,语义不同,透传不缓存。
- **非文件路径**(内存流等):跳过。
- **存快照失败**:任何异常都不影响正常加载,降级为未缓存,不阻断业务。


## 四、验证

### 正确性(bit-for-bit)
- 宿主:命中 wb 的 md5 == 冷 load 基线 md5(`312ee250…`),2,501,211 个单元格的坐标/值/类型逐个一致。
- 结构完整:merged_cells / data_validations / freeze_panes / conditional_formatting / _external_links 在命中 wb 上全部可访问。
- 容器内:业务校验(TP-13 `verify_xlsx_enhanced.py`)Success 100% 通过。

### 性能

**宿主(代码级)**
| 项 | 值 |
|----|----|
| 冷 load | 23.9s |
| 填缓存 | 0.97s |
| **命中** | **4.6s** |
| blob | 57.7MB |

**容器内(2核4G,fixed 单任务)**
| 指标 | 基线 | 缓存 | Δ |
|------|----:|----:|----:|
| Avg Latency(首任务) | 259s | **174.9s** | **-33%** |
| Success Rate | 100% | **100%** | — |

15 次调用实际分 4 个阶段串行执行,各阶段耗时:

| 阶段 | 含哪些 TP | 基线 | 缓存 | Δ |
|------|-----------|----:|----:|----:|
| P01 inspect_prepare | 01-05(读文档/拷模板/查结构/加图表) | 55.5s | 39.5s | -16.0s |
| P02 build | 06-07(写增强脚本/原子增强) | 51.1s | 34.5s | -16.6s |
| P03 process_publish | 08-12(LibreOffice 重算/读公式/读值/导出 CSV) | 105.8s | 84.3s | -21.5s |
| P04 verify_deliver | 13-15(业务校验/汇总/断言) | 45.1s | 16.2s | -28.9s |
| **合计** | | **257.5s** | **174.5s** | **-83.0s(-32.2%)** |

P03 最重(LibreOffice 重算 + 两次 openpyxl load 在此阶段,见第五节),但其中的 load 部分被缓存命中(TP-09/10)省下;P01/P02 的模板/中间版本 load 由 save-patch 链命中(TP-05/07);P04 因 TP-13 命中(key 修复 + comment 保留)降幅最大。

per-call 命中情况:

| TP | 基线 | 缓存 | 说明 |
|----|----:|----:|------|
| TP-04 | 29.7 | 33.0 | MISS(模板首 load + 填充) |
| **TP-05** | 25.6 | **6.4** | **HIT**(内容指纹命中 TP-04) |
| **TP-07** | 51.0 | **34.3** | **load HIT**(TP-05 save 填)+ enhance + save |
| TP-08 | 62.6 | 69.4 | 两次 load 均 MISS+fill(见第五节) |
| **TP-09** | 20.9 | **6.5** | HIT |
| **TP-10** | 20.5 | **6.5** | HIT |
| **TP-13** | 24.5 | **9.8** | **HIT**(key 归一化 + comment 保留,见第六节) |
| **TP-14** | 20.6 | **6.3** | HIT |

6 次命中(TP-05/07-load/09/10/13/14)各省 ~14-20s;未命中的填充开销 ~3-5s/次;净 **-83s**。

## 五、TP-08 分析:不是 LibreOffice 瓶颈

TP-08 的 `recalc.py` 在 LibreOffice 重算**之后**做了**两次 openpyxl 全量 load**:
1. `load_workbook(data_only=True)` —— 遍历 2.5M 单元格查 `#VALUE!` 等错误。
2. `load_workbook(data_only=False)` —— 再遍历一次数公式。

实测拆分(2核4G 容器内单跑 recalc.py):

| 段 | 耗时 |
|----|----:|
| LibreOffice soffice 重算 | ~16s |
| load(True) 查错误 | ~22s |
| load(False) 数公式 | ~23s |
| **合计 TP-08** | **~61s** |

所以 TP-08 **~70% 是 openpyxl load**(两次),LibreOffice 重算只 ~16s(Raw_Sample 表无公式,只有汇总表几个公式,重算很快)。"TP-08 是 LibreOffice 黑盒天花板"的假设不成立。

**为什么这两次 load 缓存救不了:**

- 缓存只能省"重复加载"——同一个文件、同一种读法(读公式 or 读值)被加载过、第二次起才命中。
- TP-08 的两次 load 是**重算后文件的"头两次读取"**,而且两种读法各读一次:查错误要读值、数公式要读公式。两种读法产出不同的单元格值,是两份独立的缓存条目,各自都是首次 → 都 miss。
- 在 TP-08 之前没有任何调用读过"重算后"的文件:TP-07 存的是重算前版本,TP-08 的 LibreOffice 重算才生成重算后版本,这两次 load 是头一个碰它的,所以没法靠"前面有人读过"来命中。
- 这两次 load 都在 `recalc.py` 脚本里,脚本是 recipe 的一部分(冻结),不能改它把两次合并成一次。

这两次 miss 顺带把缓存填了,让后面的 TP-09(读公式)/TP-10(读值)各命中一次——这是缓存从 TP-08 能拿到的极限。

## 六、局限与后续

> TP-13 此前 miss,是两个 bug 叠加,现已修复(命中 9.8s):① **key bug**——key 把"没传 read_only"(None)和"显式传 read_only=False"当不同键,TP-09 没传、TP-13 传了 → 不命中;已把 key 归一化到真实默认值。② **正确性 bug**——缓存只存了 value/data_type/style,没存 `cell._comment`/`_hyperlink`,命中重建的单元格没注释 → `source_comments` 校验挂(曾误判为"图表丢失");已每格多存 `_comment`/`_hyperlink`,`getattr` 兜底 MergedCell(其 `__slots__` 无 `_hyperlink`)。

1. **TP-08 的两次 load 无法缓存**(详见第五节):都是重算后文件的首次读取、且分属两种读法,缓存只能救重复、救不了首次;合并它们要改 `recalc.py`(recipe 脚本,冻结)。
2. **miss 的 fill 开销**:TP-04/05/07 的模板/中间版本只 load 一次就丢,缓存白付 ~3s 填充。可加启发(小文件或无后续 hit 的不填)省 ~9s。
3. **save-patch 的 data_only 维度**:save 填缓存只填 wb 加载时的那个 data_only 模式;另一模式的 load 仍 miss。

## 七、文件与复现

| 文件 | 作用 |
|------|------|
| `patches/openpyxl_cache.py` | 缓存核心(`cached_load_workbook`、`cached_save`、`_rebuild_cells`、`install`) |
| `patches/oxlcache.pth` | `.pth` 注入(内容 `import openpyxl_cache`) |
| `patches/Dockerfile.cached` | 镜像 overlay(一层) |
| `config/common/document-xlsx-cached.yaml` | cached 配置(image: cached,fixed,duration 260) |

```bash
ssh j; cd ~/yxy/document-bench; source venv/bin/activate
bench-core --provider docker --config config/common/document-xlsx-cached.yaml --cleanup
bench-core --provider docker --config config/common/document-xlsx-cached.yaml -n 1   # cached
bench-core --provider docker --config config/common/document-xlsx.yaml -n 1          # 基线(无缓存)
```
报告看 `results/document/xlsx/document_xlsx_bench_*.txt` 的 `[Step-Level Timing]`;per-call 时序看日志 `[CALLTIMINGS]` JSON。
