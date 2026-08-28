# XLSX openpyxl 共享字符串解析 fast path 优化报告

> 日期: 2026-08-28 ｜ 场景: 2核4G docker 容器,XLSX 文档基准(document-xlsx),recipe 冻结
> 结论: 容器内验证通过,**冷 load 24s → 21.85s(省 ~2s);叠加缓存后单任务 189.9s → 184.2s(-29%),warm avg 171.9s(-34%),业务校验 100% 通过(bit-for-bit)**

## 一、概要

openpyxl 加载工作簿时,共享字符串表(sharedStrings.xml,190K 条)的解析用 `Text.from_tree(node).content` 对每条字符串做一次反射式反序列化,是冷 load 里 `from_tree` 热点的全部来源。本工作簿的共享字符串 **100% 是普通串 `<si><t>text</t></si>`(无富文本 `<r>`)**,可直接 `node.find('t').text` 取值,跳过 `from_tree` 反射。优化后 sst 解析 **2.8x(1.68s→0.59s)**,bit-for-bit 一致,叠加缓存后容器综合 **184.2s(-29%)**。

## 二、定位:from_tree 热点在哪

cProfile(冷 load ~24s)显示 `from_tree` 2.45s tottime / 801K 调用。查调用者:

| 调用者 | 调用数 | cumtime |
|--------|------:|------:|
| **`strings.py:10 read_string_table`(共享字符串表)** | **190,693** | **2.510s** |
| 其余(stylesheet/chart/page 等) | <60 | <0.01s |

→ `from_tree` 的全部开销在 **共享字符串表解析**,每条 `<si>` 一次 `Text.from_tree(node).content`。

注:`parse_cell` 里也有一行 `Text.from_tree(child).content`(inlineStr 分支),但本工作簿 **inlineStr 单元格 = 0**(sheet1 = 1.7M 数字 + 800K 共享字符串 + 0 inlineStr),所以那行 0 调用、0 收益。热的 `Text.from_tree` 在 `read_string_table`,不在 parse_cell。

## 三、优化:fast path 跳过反射

原 `read_string_table`:
```python
for _, node in iterparse(xml_source):
    if node.tag == STRING_TAG:
        text = Text.from_tree(node).content  # 反射反序列化,每条一次
        text = text.replace("x005F_", "")
        node.clear()
        strings.append(text)
```

`Text.from_tree` 是 openpyxl 的 `Serialisable` 反序列化(反射、走描述符、可处理富文本 `<r>`)。但普通串 `<si><t>text</t></si>` 的内容就是直接子元素 `<t>` 的文本,无需反射。

fast path:
```python
for _, node in iterparse(xml_source):
    if node.tag == STRING_TAG:
        t = node.find(TTAG)  # 直接 <t> 子元素
        text = (
            (t.text or "")
            if t is not None  # 普通串:直接取
            else Text.from_tree(node).content  # 富文本 <r>:回退反射
        ).replace("x005F_", "")
        node.clear()
        strings.append(text)
```

- 普通串(`<si>` 有直接 `<t>`):`node.find('t').text`,一次 Element find,跳过 from_tree。
- 富文本(`<si>` 无直接 `<t>`,有 `<r>`):回退 `Text.from_tree(node).content`,行为不变。
- 同样做 `x005F_` 替换,结果一致。

本工作簿 190,693 条全是普通串(0 富文本),fast path 覆盖 100%。

## 四、验证

**bit-for-bit**:
- `read_string_table`(原)与 fast path 在同一 sst 上各跑一遍,产出列表 `len == 190,693`,`s_orig == s_fast`(逐条相等)。
- 容器内业务校验(TP-13)Success 100%。

**性能**:
| 项 | 原 | fast path |
|----|---:|---:|
| sst 解析 wall | 1.68s | **0.59s(2.8x)** |
| 冷 load(宿主) | ~24s | **21.85s(省 ~2s)** |

## 五、结果(容器内,2核4G,叠加缓存)

| 指标 | 基线 | 缓存 | **缓存 + sst fast path** |
|------|----:|----:|----:|
| 首任务 | 259s | 189.9s(-27%) | **184.2s(-29%)** |
| warm avg | 259s | 177.5s(-31%) | **171.9s(-34%)** |
| Success | 100% | 100% | **100%** |

sst fast path 在缓存基础上再省 ~5.7s。

注:这是**冷 load 优化**——缓存命中时跳过整个 XML 解析(含 sst),故 sst fast path 只在冷 load 生效。叠加缓存后,冷 load 数量已很少(TP-04 模板、TP-08 两次 load、TP-13),每冷 load 省 ~1.4s,合计 ~5.7s。

## 六、文件与复现

| 文件 | 作用 |
|------|------|
| `patches/openpyxl_cache.py` | 含 `_fast_read_string_table`,`install()` 里 patch `openpyxl.reader.excel.read_string_table` |
| `patches/oxlcache.pth` / `Dockerfile.cached` | 注入与镜像(同缓存报告) |

复现(sst 单测):
```python
from openpyxl.reader.strings import read_string_table
# fast path 见 patches/openpyxl_cache.py:_fast_read_string_table
# 对比:read_string_table(z.open("xl/sharedStrings.xml")) vs _fast_read_string_table(...)
# len 相等、列表相等、1.68s vs 0.59s
```
容器综合:`bench-core --provider docker --config config/common/document-xlsx-cached.yaml -n 1`。
