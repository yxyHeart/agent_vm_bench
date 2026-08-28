# XLSX openpyxl 加载火焰图分析报告

> 日期: 2026-08-28
> 工具: py-spy 0.4.2(flamegraph SVG)
> 对象: openpyxl `load_workbook("/tmp/xlsx_template.xlsx", data_only=False)` 单次加载,2.96M 行 / 2.5M 单元格
> 两张图:`docs/flames/before_cold_load.svg`(优化前,缓存关,冷加载)/ `after_cache_hit.svg`(优化后,缓存命中)

## 一、采样概况

| | BEFORE(冷加载,缓存关) | AFTER(缓存命中) |
|---|---:|---:|
| 总采样 | 2333 | 597 |
| wall time | ~24s | ~5s |
| 含义 | 完整 XML 解析 + 单元格构造 | 跳过 XML 解析,仅重建单元格 |

采样数差距即耗时差距:命中后只做"造 2.5M 个 Cell 对象",XML 解析段全跳过。

## 二、BEFORE 火焰图:XML 解析主导

按采样数排序的顶部函数(BEFORE):

| 函数 | 文件 | 采样 | 占比 | 归类 |
|------|------|----:|----:|------|
| parse | _reader.py:125 | 1444 | 62% | XML 解析循环 |
| iterator | ElementTree.py:1241 | 985 | 42% | iterparse 事件拉取 |
| feed | XMLParser(expat C) | 889 | 38% | expat 逐字符解析 |
| parse_row | _reader.py:282 | 423 | 18% | 行解析 |
| `<listcomp>` | _reader.py:303 | 413 | 18% | 行内单元格列表 |
| parse_cell | _reader.py:189 | 391 | 17% | 单单元格解析 |
| bind_cells | _reader.py:367 | 361 | 15% | 绑定到 Cell 对象 |
| read_string_table | strings.py:10 | 175 | 7.5% | 共享字符串表 |
| __init__ | cell.py:109 等 | 140 | 6% | Cell 构造(见下) |
| __new__ | cell_style.py:53 | 51 | 2.2% | StyleArray 重复拷贝 |

> 占比加总超 100% 因函数嵌套(父帧含子帧采样)。

**BEFORE 的结构(自顶向下):**
```
load_workbook
└─ read_worksheets → bind_all → bind_cells (361)
   └─ parse (1444) ← 整个 sheetData 的 iterparse 循环
      ├─ iterator/read_events (985) ← iterparse 事件
      │  └─ feed (889) ← expat C 解析(逐字符状态机)
      ├─ parse_row (423) → parse_cell (391) ← 每单元格抽值/类型/样式
      │  └─ coordinate_to_tuple (75) ← A1→(1,1)
      └─ __init__ (cell.py:109, 140) ← Cell 对象构造
         └─ __init__ (styleable.py:135, 80) ← super,含 StyleArray 重复拷贝
```

**关键观察:**
- **XML 解析段(parse+iterator+feed+parse_cell+parse_row)≈ 60%+** —— expat 逐字符状态机 + iterparse 事件拉取 + 每单元格抽取,是冷加载的绝对大头。
- **Cell 构造(bind_cells 下的 __init__)≈ 6%** —— 窄条,被上面的大宽条压住,视觉上容易漏(悬停 tooltip 看 `cell.py:109` 区分)。
- **StyleArray 重复拷贝(__new__ cell_style.py:53)≈ 2%** —— bind_cells 里每格 `StyleArray(style_array)` 拷一份 9-int array,OP3 优化点。
- **共享字符串表 read_string_table(175)≈ 7.5%** —— sst 解析的 `Text.from_tree` 反射(已被 sst fast path 优化,但本报告对应未开 sst 优化的基线)。

## 三、AFTER 火焰图:只剩重建

顶部函数(AFTER,缓存命中):

| 函数 | 文件 | 采样 | 占比 | 归类 |
|------|------|----:|----:|------|
| _rebuild_cells | openpyxl_cache.py:89 | 417 | 70% | 缓存重建循环 |
| __init__ | cell.py:109 等 | 276 | 46% | Cell 构造 |
| cached_load_workbook | openpyxl_cache.py | 495 | 83% | 缓存壳(pickle.load+rebuild) |

**AFTER 的结构:**
```
cached_load_workbook (495)
├─ pickle.load (~0.3s) ← 反序列化无单元格 wb(小)
└─ _rebuild_cells (417) ← 重建 2.5M 个 Cell
   └─ __init__ (cell.py:109, 276) ← Cell 对象构造
      └─ __init__ (styleable.py, 少量) ← super(跳过 StyleArray 拷贝,直接共享)
```

**关键观察:**
- **parse / iterator / feed / parse_cell / parse_row / read_string_table 全部消失** —— XML 解析段整块没了(命中即跳过)。
- **_rebuild_cells(417)+ Cell.__init__(276)** —— 命中后只剩"造 2.5M 个 Cell 对象",这是纯 Python 构造的物理下限,无法再降(除非 C 扩展)。
- **StyleArray 重复拷贝没了** —— _rebuild_cells 直接 `cell._style = st_list[sid]` 共享样式表条目(OP3),styleable 的 __init__ 采样大幅减少(BEFORE 80 → AFTER 极少)。

## 四、前后对比:跳过了什么、保留了什么

| 段 | BEFORE 采样 | AFTER 采样 | 命中后 |
|------|----:|----:|------|
| XML 解析(parse/feed/iterator/parse_cell/parse_row) | ~3300 | 0 | **整块跳过** |
| 共享字符串表(read_string_table) | 175 | 0 | **跳过**(在 cell-less wb 里) |
| StyleArray 重复拷贝(__new__) | 51 | 0 | **跳过**(直接共享) |
| Cell 构造(__init__ cell.py) | 140 | 276 | **保留**(2.5M 对象必须造) |
| _rebuild_cells | 0 | 417 | **新增**(重建循环) |
| pickle.load | 0 | 少量 | **新增**(反序列化小 wb) |

**一句话:命中后跳过了 ~3300 采样的 XML 解析 + 175 采样的 sst + 51 采样的 StyleArray 拷贝,只保留 ~276 采样的 Cell 构造 + ~417 采样的重建循环。** 这正是 24s→5s(4.8x)的来源。

## 五、Cell.__init__ 为什么 BEFORE 里窄、AFTER 里宽

- **BEFORE**:Cell.__init__ 只有 ~140 采样(6%)——因为 ~94% 的时间花在它前面的 XML 解析(parse/feed/parse_cell)上,构造只是末尾一小步。火焰图里它被 bind_cells 盖着、上面是大宽条,视觉上不显眼。
- **AFTER**:XML 解析没了,剩下的几乎全是 Cell.__init__(276 采样,46%)+ _rebuild_cells 循环。它从"被压住的窄条"变成"主帧之一"。

这解释了优化前后火焰图形态的根本变化:**从"XML 解析主导"变成"对象构造主导"**。Cell 构造的绝对耗时其实没变多少(BEFORE ~1.8s tottime,AFTER 仍要造 2.5M 个),只是它前面的 XML 解析段被砍掉了,所以它在图里的相对占比放大了。

## 六、剩余可优化点(从 AFTER 图看)

AFTER 图里 `_rebuild_cells`(417)+ `Cell.__init__`(276)占了 ~90%。要再砍命中时间,只能动这两块:

1. **Cell.__init__ 本身**(~1.3µs/cell × 2.5M):透传 data_type 免二次置(OP2,~0.2-0.4s)、用 `__new__`+直接 slot 赋值绕过 `__init__`、延迟 `_hyperlink`/`_comment` 初始化。预期再省 ~0.5-1s(命中 5→~4s)。
2. **_rebuild_cells 循环**(解包+dict set):列表推导 + 批量赋值优化。边际。
3. **少造 Cell**:不物化全部(改 read_only 语义)——但 recipe 要 `ws.cell(r,c)`,不能。

这些都是边际优化(单次命中 5→~4s),且命中在整任务里只占一小部分(大部分是 LibreOffice 重算 + 冷加载),对全任务收益有限。

## 七、图文件

- `docs/flames/before_cold_load.svg` —— 优化前(冷加载,缓存关,2333 采样 / ~24s)
- `docs/flames/after_cache_hit.svg` —— 优化后(缓存命中,597 采样 / ~5s)

浏览器打开,交互式:点击放大、Search 框搜函数名/文件、悬停看 tooltip(函数+文件:行+采样数+占比)。
