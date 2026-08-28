# XLSX 端到端耗时分析(per-call 实测)

> 1 个任务、1 容器、`--detect --round-count 1`(单次实测,无重复采样)。
> per-call 计时由 `document.py` 的 `_execute_phase` 内 `perf_counter` 埋点产出(纯增量,命令/控制流不变)。

## 15 个测试点实测

| TP | 阶段 | 函数 | 耗时 | 占比 | 操作描述 |
|----|------|------|-----:|-----:|----------|
| TP-01 | P01 inspect_prepare | read | 0.052s | 0.0% | 读取 xlsx skill 文档 |
| TP-02 | P01 inspect_prepare | exec | 0.052s | 0.0% | 读取校验脚本源码 |
| TP-03 | P01 inspect_prepare | exec | 0.054s | 0.0% | 复制模板为工作副本 |
| TP-04 | P01 inspect_prepare | exec | 29.7s | 11.5% | openpyxl 全量加载(结构检查) |
| TP-05 | P01 inspect_prepare | exec | 25.6s | 10.0% | openpyxl 加载并写入图表 |
| TP-06 | P02 build | write | 0.16s | 0.1% | 写入增强脚本 enhance_workbook.py |
| TP-07 | P02 build | exec | 51.0s | 19.8% | 原子化执行增强(load+修改+save) |
| TP-08 | P03 process_publish | exec | 62.6s | 24.3% | LibreOffice 公式重算(2.96M 行) |
| TP-09 | P03 process_publish | exec | 20.9s | 8.1% | openpyxl 加载(data_only=False,读公式) |
| TP-10 | P03 process_publish | exec | 20.5s | 8.0% | openpyxl 加载(data_only=True,读计算值) |
| TP-11 | P03 process_publish | exec | 0.094s | 0.0% | 读取重算结果 JSON |
| TP-12 | P03 process_publish | exec | 1.7s | 0.7% | 导出 CSV(read_only 流式) |
| TP-13 | P04 verify_deliver | exec | 24.5s | 9.5% | openpyxl 加载(业务校验) |
| TP-14 | P04 verify_deliver | exec | 20.6s | 8.0% | openpyxl 加载(汇总特征) |
| TP-15 | P04 verify_deliver | exec | 0.078s | 0.0% | 断言交付物非空 |

## 阶段小计

| 阶段 | 耗时 | 占比 |
|------|-----:|-----:|
| P01 inspect_prepare | 55.5s | 22% |
| P02 build | 51.1s | 20% |
| P03 process_publish | 105.8s | 41% |
| P04 verify_deliver | 45.1s | 17% |
| **总计** | **257.5s** | 100% |

## 关键发现(纠正"recalc 是瓶颈"的判断)

| 类别 | 耗时 | 占比 |
|------|-----:|-----:|
| **openpyxl 全量加载(7 次: TP-04/05/07/09/10/13/14)** | **192.7s** | **74.8%** |
| LibreOffice 公式重算(TP-08) | 62.6s | 24.3% |
| 其余 I/O(TP-01/02/03/06/11/12/15) | ~2.2s | 0.9% |

实测推翻了 phase 级直觉:recalc 只占 24%,**openpyxl 反复全量加载才是大头(~75%)**。

## 根因分析:openpyxl 与 LibreOffice 为何占比大

### openpyxl 占 75%(~192.7s / 7 次)——链路处理低效

不是"单次特别慢",而是几个因素叠加放大:

1. **纯 Python + 全量物化**:xlsx 本质是"ZIP 套 XML"。`load_workbook`(非 `read_only`)要解压→解析 `sheetN.xml`→**每个单元格实例化成一个 Python Cell 对象**(含样式 dict、refcount、堆分配)。2.96M 行 × 多列 = 数千万 Cell 对象,纯 Python 走 lxml 解析 + 创建海量对象,这是慢的本质。
2. **全量 vs 流式是关键开关**:同一份工作簿,`read_only=True` 的 TP-12 只 1.7s,全量的 TP-09 要 20.9s——**~12× 差距**。证明慢的不是"读文件",而是把整表物化进内存这棵对象树;`read_only` 是生成器流式扫,不建对象树。
3. **重复 7 次,跨进程无复用**:同一 2.96M 行工作簿被加载 7 次(TP-04/05/07/09/10/13/14),每次都是独立 `python3` 进程(`docker exec`),内存里的对象树用完即弃,无法跨调用共享。7 × ~20-50s 量变到质变。
4. **单线程**:openpyxl 加载单线程,2vCPU 容器加载时第二核闲置——没榨干资源。
5. **数据规模是放大器**:每 Cell 成本固定(纯 Python 对象开销)~µs 级,2.96M 行 × 列数 → 单次 ~20s。行数小 1000×(几千行),单次就 <0.1s,冗余 7 次也无所谓;到百万级,7× 就吃掉 75%。

**本质**:openpyxl 的大 = 纯 Python 全量物化 × 冗余 7 次 × 百万行规模,属链路处理低效,可优化(切 read_only / 减冗余)。

### LibreOffice 占 24%(62.6s / 1 次)——负载本身重

它占得大是因为干的活真重,不是低效:

1. **真正的全表公式重算**:recalc 不是读,是**重新求值工作簿里所有公式**。模板里有引用 Raw_Sample(2.96M 行)的聚合/查找/汇总公式,recalc 要遍历依赖图、对每个公式单元重算,很多公式扫大范围——货真价实的 O(百万) 计算。
2. **套件重**:LibreOffice 是完整办公套件(老 C++ 代码库),headless 也要启 VCL/calc 引擎 + 自己的 OOXML 过滤器加载文档 + 保存。`recalc.py` 还要 fork `soffice` 子进程(冷启动 ~1-2s)。
3. **单次 C++ 反而比 openpyxl 单次便宜**:这 62.6s 含了**加载+全表重算+保存**整份 2.96M 工作簿,却只是 ~3× 单次 openpyxl 全量加载(~20s)。即原生 C++ 的 OOXML 解析+重算引擎,单位效率高于 openpyxl 纯 Python 物化。它"大"纯粹是任务本身重(全表重算),不是实现烂。

**本质**:LibreOffice 的大 = 任务本身就是百万行重算,C++ 实现已相对高效,优化它 = 改变被测负载,不在优化范围。

### 对比

| | 大的原因 | 性质 | 能不能动 |
|---|---|---|---|
| openpyxl 75% | 纯Python物化 + 冗余7次 + 百万行 | 链路处理低效 | 能(read_only / 减冗余) |
| LibreOffice 24% | 真重算百万行公式 | 负载本身 | 不能(改了=换被测对象) |

数据指向明确:**该动 openpyxl 的重复全量加载,不该动 LibreOffice recalc**。

→ 优化方案见 [`docs/xlsx-optimization-plan.md`](xlsx-optimization-plan.md)。
