# lxml 替代 stdlib XML 解析:证伪实验报告

## 目标

openpyxl 全量 `load_workbook` 的两圈活之一是"读 XML"(stdlib expat + ElementTree,~14s,占 cProfile ~36%,expat `feed` 是 #1 热点)。stdlib 的 `xml.etree.ElementTree.iterparse` 是纯 Python 包装层 + C `_elementtree`。设想:换成 lxml 的 C 实现 `lxml.etree.iterparse`,把读 XML 这圈做快。

## 前提:openpyxl 3.1.5 的 lxml 路径是死的

openpyxl 有 `LXML=True` 代码路径(`functions.py` 在 `LXML` 为真时用 `lxml.etree`),但:

- **容器内 `LXML=False`**——openpyxl 安装时探测不到 libxml2,`setup.py` 把 `LXML` 标志写成 `False`,整条 lxml 分支永远不走。
- 即便宿主装了 lxml,`iterparse` 调用点(`functions.py:40`)在 `if LXML:` 块**外**——`LXML=False` 时 `iterparse` 被 `from xml.etree.ElementTree import iterparse` 覆盖,stdlib 兜底。

所以光设 `LXML=True` 没用(`iterparse` 不读这个标志)。要真换成 lxml,得 monkey-patch `_reader.iterparse`。

## 实验

### 环境

- 宿主 `venv-clean`(Python 3.11),装了 lxml 6.1.2。
- 测试文件:`/tmp/xlsx_template.xlsx`(2.5M 行,产物同基准模板)。
- 基线对照:同一 venv-clean、同文件、stdlib iterparse。

### Patch(monkey-patch 三个调用点)

openpyxl 的 `iterparse` 从 `openpyxl.xml.functions` 导入,但调用方(`worksheet/_reader.py`、`reader/strings.py`)都做 `from openpyxl.xml.functions import iterparse` 绑了本地名,所以三个点都要 patch:

```python
import lxml.etree
import openpyxl.xml.functions as funcs
import openpyxl.worksheet._reader as ws_reader
import openpyxl.reader.strings as strings
funcs.iterparse = lxml.etree.iterparse
ws_reader.iterparse = lxml.etree.iterparse
strings.iterparse = lxml.etree.iterparse
```

### 结果(各 3 次,宿主 venv-clean Python 3.11 + lxml 6.1.2)

| 方案 | wall(min) | mean | md5 |
|---|---:|---:|:---:|
| stdlib `ElementTree.iterparse`(基线) | 25.78s | 25.89s | `895bf0c5dd3c` |
| lxml `etree.iterparse`(monkey-patch) | **40.81s** | 41.13s | `895bf0c5dd3c` |

md5 完全一致 → 输出 bit-for-bit 忠实,没改语义。但 lxml **慢 ~59%**(+15s)。

## lxml 想优化哪一步

openpyxl 的 `iterparse` 流程分两层,lxml 替换的是两层一起:

| | stdlib 路径 | lxml 路径 |
|---|---|---|
| XML 解析 | expat(C)逐字符 | libxml2(C)逐字符,同样是标量状态机,无优势 |
| 建 Element 树 | expat → Python 回调 → 建 2.5M 个 Python Element 对象 | libxml2 直接建 C xmlNode 结构,跳过 Python 回调 |

lxml 的理论优化点在第二层:跳过 Python 回调 + Python Element 对象分配。但实测反而慢 59%,因为 lxml 的 Element 是 C xmlNode + Python proxy,比 stdlib 的轻量 Python Element 更重——2.5M 个更重的对象把省的回调全赔回去还倒亏。

## 原因分析

lxml 在本场景(zip 流 + 2.5M 元素)反而更慢:

1. **lxml Element 是更重的 C 对象。** stdlib ElementTree 的 Element 是 Python 对象(轻),lxml Element 是 libxml2 `xmlNode` 的 C 结构 + Python proxy。2.5M 个元素,每个都更重 → 内存更大、分配更慢、GC 更累。
2. **zip 流读取路径不适配。** openpyxl 的 `iterparse` 喂的是 zip 流(从 `.xlsx` 里读 `xl/worksheets/sheetN.xml`)。stdlib `iterparse` 直接吃 file-like,lxml 的 `iterparse` 对 zip 流的适配路径多一层拷贝/缓冲,没占到 C 解析的便宜。
3. **lxml 的优势在随机访问/XPath,不在流式逐元素遍历。** openpyxl 用 `iterparse` 是"读完即丢"的流式扫描(只要 `event='end'` 拿 cell),正是 lxml 不擅长、stdlib 已经够用的形态。

## 结论

- **lxml 是死路。** 替换 stdlib `iterparse` → lxml 在本场景慢 ~59%(25.8s → 41.1s),且 md5 忠实但方向反了。读 XML 这圈(14s)用 stdlib 已经是局部最优,换 C 解析器不赚反亏。
- **根因不是"stdlib XML 慢"。** stdlib expat C 解析本身只占 perf DSO ~6.54%(`_elementtree` 3.57%),大头在"建 2.5M 个 Element + 2.5M 个 Cell 对象"。换 lxml 把 Element 变得更重,正好踩到大头。
- **指向:** 读 XML 这圈砍不动的杠杆在于"减少要读的量"(read_only 跳过)或"整圈跳过"(缓存命中),不是"把解析器换成 C"。

## 附:数据文件

- 宿主 venv-clean 上的 stdlib vs lxml 计时(各单次,无重复)。
- 容器内 `LXML=False`、无 lxml,本实验只在宿主做(验证方向,不进容器)。
