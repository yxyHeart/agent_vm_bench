# XLSX 优化前后火焰图对比

> baseline = `xlsx_steps/`(无缓存) vs cached = `xlsx_steps_cached/`(openpyxl 磁盘缓存, 稳态命中)

## 结论

**缓存命中后, load_workbook 的热点从 XML 解析切换为 Cell 对象重建, 各步骤耗时降 60~77%。**

| 步骤 | 内容 | 降幅 | 热点变化 |
|------|------|----:|----------|
| step04 | 检查工作簿结构 | -72% | parse 36% → cached_load 63% |
| step05 | 检查图表/样式 | -77% | parse 38% → cached_load 80% |
| step07 | enhance (读+写) | ~-37% | parse 18% → 写序列化 18% |
| step09 | 查公式 | -73% | parse 46% → cached_load 81% |
| step10 | 查缓存值 | -74% | parse 46% → cached_load 85% |
| step12 | 导出 CSV | -9% | read_string_table 不变 |
| step13 | 业务验收 | -62% | parse 37% → cached_load 51% |
| step14 | 写摘要 | -70% | parse 44% → cached_load 80% |

## 优化前: XML 解析主导

所有全量 load 步骤的热点一致: `parse`(35~46%) + `iterator/feed`(expat, 33~41%) + `parse_row/parse_cell`(16~19%)。瓶颈 = XML 解析, 在 6 个步骤重复出现。

## 优化后: 只剩 Cell 重建

```
cached_load_workbook  55~85%
├─ _rebuild_cells     23~41%   ← 重建 2.5M Cell
└─ pickle.load        11~17%
```

XML 解析帧整块消失, 剩余是纯 Python 对象构造, 已到语言层下限。

## 两个不变项(设计如此)

- **step12 导出 CSV** (-9%): read_only 流式透传, 不走缓存, 采样基本持平
- **step07 写侧**: 命中后第一热点变为 `_serialize_ns_xml`(写序列化), 缓存救不了 save

## 汇总

load 侧 -70%+, save/recalc/read_only 侧不变, 加权后即端到端 -33%, 火焰图与压测结果自洽。剩余大头(LibreOffice recalc + 写序列化)不受缓存影响, 属于本方案极限。
