# XLSX 链路优化方案

> 基于 [`xlsx-e2e-timing.md`](xlsx-e2e-timing.md) 的 per-call 实测(总 257.5s)。目标:优化"链路处理"(工具调用的执行方式),不动被测负载本身,不改业务输出(P04 业务校验仍断言一致)。

## 数据背书

- **TP-12 = 1.7s**(`load_workbook(read_only=True)` 流式),证明 read_only 比全量加载快 ~12×。
- 占比:openpyxl 全量加载 74.8%(7 次)/ LibreOffice recalc 24.3% / 其余 0.9%。
- 真大头是 openpyxl **重复全量加载**,不是 recalc。

## read_only 的限制(可行性核验依据)

`read_only=True` 只支持读单元格**值**与 `merged_cells`;**不支持** `_charts`、`cell.comment`、`conditional_formatting`、`data_validations`、`freeze_panes`、`_external_links`,且不支持 `ws.cell(row,col)` 随机访问(须改 `iter_rows()`)。

逐条核实各 load 调用的访问模式后,只有 TP-09/10 两处能切 read_only;TP-04/05/07/13/14 因访问 charts/comments/dv/condfmt/freeze 或需写,read_only 不支持,属 inherent。

---

## 优化 #1:TP-09 / TP-10 切 read_only(最高 ROI)

| TP | 现状 | 访问 | read_only 可行? |
|----|------|------|----------------|
| TP-09 | `load_workbook(data_only=False)` 读公式 + `merged_cells` | `ws.cell().value`、`merged_cells.ranges` | ✓ 可行(需改 `ws.cell()`→`iter_rows(values_only=False)`) |
| TP-10 | `load_workbook(data_only=True)` 读缓存值 | `ws.cell().value` | ✓ 可行(改 `iter_rows(values_only=True)`,即 TP-12 的写法) |

- **改法**:P03 这两条 `python3 -c` 命令,`load_workbook(..., read_only=True)`,访问从 `ws.cell(r,c).value` 改为 `ws.iter_rows(min_row=,max_row=,min_col=,max_col=,values_only=...)`。
- **收益(实测)**:TP-09 20.9s→**1.72s**(12.1×),TP-10 20.5s→**1.72s**(11.9×),合计 41.4s→3.4s,**省 ~38s**。P03 阶段 105.8s→70.2s,**总任务 257.5s→222.2s(−13.6%)**。
- **保真验证**:P04 业务校验 `Success: 1`(输出 bit-for-bit 一致)。
- **根因实证**:模板 `xl/worksheets/sheet1.xml`(Raw_Sample 2.96M 行)= 123.5MB;`read_only` load 0.01s(惰性),`full` load 22.44s(全量物化该表)。全量 load 慢=物化 Raw_Sample,与读哪个 sheet 无关。优化后 TP-09/10 与 TP-12(1.70s)齐平。
- TP-09 取公式需 `values_only=False`,且 read_only 不支持 merged_cells,故手动解析该 sheet XML 重建 `MultiCellRange` 以保输出一致。

## 优化 #2:合并 TP-13 + TP-14 的全量 load

- **现状**:P04 两个脚本**各自全量 load 一次**取 features(TP-13 的 verify + TP-14 的 summary 都要 charts/comments/dv/condfmt/freeze/external_links)。
- **改法**:合成一个脚本,**一次 full load 同时做** verify + collect_features → 写 business_verification.json + execution_summary.json。
- **收益**:省掉一次全量 load ~20-24s,**省 ~20s(−8%)**。
- **风险**:中。合并 2 个 recipe 调用(15→14),须保证两个产物 JSON 内容 bit-for-bit 一致(脚本逻辑搬移即可)。

## 合计

~57s,总任务 257.5s → **−22%**(优化 #1 + #2)。

---

## 不优化项(数据背书跳过)

| 项 | 实测 | 判定 |
|----|------|------|
| per-call docker exec 税 | floor ~52-94ms ×15 ≈ 0.9s + py 冷启动 ~4.5s ≈ **5.4s(2.1%)** | 持久会话模型 ROI <3%,**不做** |
| TP-04(inspect 取 charts/condfmt/freeze) | 29.7s | read_only 不支持,**inherent** |
| TP-05(加图表,需写)/ TP-07(增强,需写) | 25.6s / 51.0s | 需写 + 取 features,**inherent** |
| TP-13 剩余 full load / TP-14 | ~20-24s | 取 features,read_only 不支持(优化 #2 已覆盖合并) |
| TP-08 LibreOffice recalc | 62.6s | 负载本身,**不动** |

## 架构级备选(大改,后续评估)

- read_only 仍是纯 Python 流式解析;若需更快,可换 Rust 后端 `python-calamine`(读 xlsx 比 openpyxl 快 5-10×),但替换依赖 + 风险,属大改,先做 #1/#2 再评估。

## 实施顺序

1. 优化 #1(TP-09/10 切 read_only)——低风险、最高 ROI,先做并重测验证。
2. 优化 #2(合并 TP-13/14 load)——中风险,#1 验证后再做。
3. 重测:per-call 埋点再跑一轮,对比 15 点耗时,确认收益与输出一致。
