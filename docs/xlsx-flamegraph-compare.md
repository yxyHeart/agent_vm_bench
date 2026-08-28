# XLSX openpyxl 加载火焰图对比

> py-spy 0.4.2 flamegraph,单次 `load_workbook`(2.96M 行 / 2.5M 单元格)

## 顶部热点函数对比

### BEFORE(冷 load,缓存关,2333 采样 / ~24s)—— XML 解析段主导:

| 函数 | 采样 |
|------|----:|
| parse(XML 解析循环) | 1444 |
| iterator(ElementTree 迭代) | 985 |
| feed(expat 解析) | 889 |
| parse_row | 423 |
| parse_cell | 391 |
| bind_cells | 361 |
| read_string_table(共享字符串) | 175 |
| \_\_init\_\_(Cell 构造) | 395 |

### AFTER(命中,缓存开,597 采样 / ~5s)—— 只剩重建,XML 解析全消失:

| 函数 | 采样 |
|------|----:|
| _rebuild_cells(重建) | 417 |
| \_\_init\_\_(Cell 构造) | 276 |
| cached_load_workbook(缓存壳) | 495 |

`parse` / `iterator` / `feed` / `parse_cell` / `parse_row` / `bind_cells` / `read_string_table` —— 命中后**全部消失**(跳过 XML 解析),只剩 `_rebuild_cells` + Cell 构造。

## 图文件

- `docs/flames/before_cold_load.svg`
- `docs/flames/after_cache_hit.svg`

浏览器打开,交互式:点击放大、Search 框搜函数名、悬停看 tooltip(函数+文件:行+采样数+占比)。
