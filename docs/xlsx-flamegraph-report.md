# XLSX 优化前后火焰图对比报告

> 采集条件: py-spy 0.4.2, 50Hz, 同一容器镜像（`ubuntu-document-bench:xlsx-combo-pyspy`），仅环境变量区分两组（stock: `OPENPYXL_CACHE=0 OPENPYXL_SPEEDUPS=0`）。
> 图源: `docs/flames/xlsx_tps_stock/`（优化前）与 `docs/flames/xlsx_tps_combo/`（优化后）。
> 跳过零头/不涉及优化的测试点: TP-01/02/03（读文档/cat/cp）、TP-06（写脚本）、TP-11（cat JSON）、TP-15（test 断言）。

## 对比表（含函数级变化分析）

| 测试点 | 优化前 (stock) | 优化后 (combo) | 函数级变化分析 |
|--------|---------------|----------------|----------------|
| **TP04**<br>结构检查<br>(MISS) | `TP04_structure.svg`<br>852 样本 ~17s<br>热点链: `load_workbook`→`read`→`read_worksheets` 79.5% | `TP04_structure.svg`<br>801 样本 ~16s<br>同链 73.7%，帧结构几乎相同 | **解析路径未变但变快**: 冷缓存 MISS 仍走原生解析链（`openpyxl_cache.py:170`→MISS 分支），节省来自 Cython 融合循环——`bind_cells` C 段 py-spy 采不到（盲区），故帧形似而总样本略降 |
| **TP05**<br>图表检查<br>(HIT) | `TP05_charts.svg`<br>864 样本 ~17s<br>`read_worksheets` 全量解析 80.9% | `TP05_charts.svg`<br>220 样本 ~4.4s<br>`_rebuild_cells` 51.8% + `max_row` 3.2% | **解析链被整体替换**: `read_worksheets`→XML 逐格解析 消失，换成 `cached_load_workbook:157`（HIT 分支）→`_rebuild_cells`（直填槽位重建）；残余热点是 `max_row/max_column` 维度计算等轻量帧 |
| **TP07**<br>增强 | `TP07_enhance.svg`<br>729 样本 ~14.6s*<br>save 46.4% + load 44.0% | `TP07_enhance.svg`<br>810 样本 ~16.2s<br>**save 74.6%**，load 段不可见 | **热点完成交接**: load 命中后只剩 writer 链 `save_workbook`→`write_data`→`_write_worksheets`；save 是两层优化都不碰的写入路径，占比被动升高（优化剩余最大单项） |
| **TP08**<br>公式重算 | `TP08_recalc.svg`<br>650 样本 ~13s<br>`recalc` 40.4% + load 40.4%（`bind_all` 36.2%） | `TP08_recalc.svg`<br>774 样本 ~15.5s<br>`recalc` 44.6% + load 35.9%（`bind_all` 28.1%） | **结构相似（含一次 MISS）**: soffice 写回新文件→指纹变→缓存失效，重算后仍走全量解析（`:170` MISS 分支）；soffice 子进程不在图内；`bind_all` 降 8pct 来自 speedups |
| **TP09**<br>读公式<br>(HIT) | `TP09_formulas.svg`<br>748 样本 ~15s<br>`read_worksheets` 83.2% | `TP09_formulas.svg`<br>211 样本 ~4.2s<br>`_rebuild_cells` 48.3% + `_key`/`_content_fingerprint` 0.5% | 同 TP05: 解析链换成重建链；可见极小的指纹计算帧（`_content_fingerprint` 首尾 4MB md5），证明命中判定开销可忽略 |
| **TP10**<br>读值<br>(HIT) | `TP10_values.svg`<br>749 样本 ~15s<br>`read_worksheets` 82.9% | `TP10_values.svg`<br>220 样本 ~4.4s<br>`_rebuild_cells` 43.2% + import 段 1.8% | 与 TP09 同构；`_find_and_load` 帧暴露 combo 多出的 openpyxl_cache 模块导入（一次性，~0.04s） |
| **TP12**<br>导 CSV | `TP12_csv.svg`<br>51 样本 ~1s<br>`load_workbook` 100%（`excel.py:291`） | `TP12_csv.svg`<br>52 样本 ~1s<br>同左 90.4% | **两组帧完全同构**: read_only 流式走 `excel.py:291`（非 303 全量分支），缓存不包装流式、speedups 只加速全量绑定——验证了两层的适用边界 |
| **TP13**<br>业务校验<br>(HIT) | `TP13_verify.svg`<br>925 样本 ~18.5s<br>`verify_formula_workbook` 70.8% → 全量 load 链 | `TP13_verify.svg`<br>335 样本 ~6.7s<br>`verify_formula_workbook` 62.4% → `_rebuild_cells` 25.1% | verify 逻辑帧占比基本不动（70.8→62.4%），内部 load 从 `read_worksheets` 全量解析换成 `:157` HIT→`_rebuild_cells`，是时长 3 倍差距的唯一来源 |
| **TP14**<br>汇总特征<br>(HIT) | `TP14_summary.svg`<br>732 样本 ~14.6s<br>`collect_features` 80.3% → 全量 load 链 | `TP14_summary.svg`<br>204 样本 ~4.1s<br>`collect_features` 95.6% → `_rebuild_cells` 38.7% | 同 TP13: 特征收集逻辑不变，load 段被缓存重建替换，占比升高因总时长缩短 |

\* TP07 stock 组采用轮询 attach，启动偏晚错过部分 load 段，样本略少（火焰图目录 README 已注明）。

## 贯穿性结论

1. **stock 组所有全量读的图都是同一条巨型解析链** `load_workbook→read→read_worksheets`；combo 组 HIT 图统一换成 `cached_load_workbook:157→_rebuild_cells` 短链——这是命中场景 -71%~75% 时长的函数级证据。
2. **唯二不变的两个测试点恰好圈出优化边界**: TP04（MISS，冷解析走原生链，收益来自 Cython 盲区加速）与 TP12（read_only 流式，两层均不适用）。

## 读图须知（采集方式的固有偏差）

1. **stock 组图里的 `cached_load_workbook` 帧是 wrapper 壳**: stock 用"组合镜像+环境变量关闭"，`.pth` 注入的包装函数仍在调用栈上，但内部透传原生 `_original_load`，行为等价（原生解析 ~17s 采样与 stock 耗时吻合）。
2. **speedups 的收益体现为样本总数下降**: Cython C 融合循环是采样盲区，combo 的 MISS 图帧结构与 stock 相似但 wall time 已缩短。
3. **TP08 的 soffice 段缺失**: py-spy 只采主 python 进程，soffice 是其子进程，主进程阻塞在 wait 期间样本记为 errors。
4. TP13/14 的增强脚本是 recipe 原版 10KB `enhance_workbook.py`（从 recipe JSON 提取），保证 verify 检查的 `Executive_Summary` 等结构齐全，全链 rc=0。
