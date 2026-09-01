# XLSX 通用优化报告：openpyxl speedups 扩展

> 日期: 2026-08-31 ｜ 场景: 2核4G docker 容器, XLSX 文档基准, 发行版 CPython 原样
> 约束: **不改 workflow、不识别特定 Sheet/文件结构、不跳过任何步骤**——只优化同一套 openpyxl 调用在底层的执行效率, 任何新的 XLSX 流程进来自动受益。
> 结论先行: 推荐组合 = **发行版 CPython 原样 + openpyxl_speedups 扩展**。微基准: 冷加载 **22.3s → 17.9s (-19.6%)**; 端到端(同日同窗口 A/B): **258.3s → 217.9s (-15.4%), Success 100%**。zlib-ng、CPU 绑核、LibreOffice 并发参数三项证伪。此前四轮 -77.7% 的工作负载感知层已归档为实验数据, 与本路线互斥。

## 一、背景: 钱花在哪

PMU 画像(此前已采集): 处理约 250 万 Cell 执行了 **~190B 条指令**, IPC 2.5, libpython 占 87%, libexpat 仅 6.5%, 无 memory stall、无 syscall 瓶颈。结论: 瓶颈不是"指令跑得慢", 是**每个单元格都在支付一套 Python 协议税**(对象分配/方法分发/中间 dict/字典查找)。

冷加载的一次拆解(发行版解释器): 纯 iterparse 无操作循环(仅 expat+Element 创建)对该 123MB sheet 实测 **~7.6s**——即 XML→Element 是地板, 其余全部是 Element→Cell 模型转换的 Python 开销。这就是优化对象。

## 二、方案: openpyxl_speedups 扩展

### 2.1 问题: 每个 Cell 的"Python 协议税"

openpyxl 原生加载一个 sheet 的链路:

```text
XML 字节 → expat(C) → Element 对象树 → Python 循环逐格处理 → Cell 对象
```

每处理一个格子(本工作簿 250 万次), Python 层要支付:

| 开销 | 次数 |
|---|---|
| `parse_cell()` 方法调用 + 返回值打包成 dict(5 个键) | 1 次/格 |
| `bind_cells()` 再从 dict 逐键取出 5 次 | 1 次/格 |
| `coordinate_to_tuple("AB123")`: 切片、反转、字典查找 | 1 次/格 |
| `element.find/findtext` 扫描子树 3 次(v/f/is 各一次) | 3 次/格 |
| `Cell.__init__` 构造 + 属性赋值 | 1 次/格 |
| 每格复制一份 StyleArray(正确性必需, openpyxl 样式是原地改) | 1 次/格 |

这些在 CPython 里全是解释器字节码: 对象分配、引用计数、方法分发、dict hash。250 万格 × 每格几十次解释器操作 = 190B 指令的主体。地板测量也印证: 纯 expat+Element 创建只要 7.6s, 冷加载却要 25s——多出的 ~17s 全是 Element→Cell 这一圈的 Python 协议税。

### 2.2 优化: 把整个循环编译成 C

核心思想一句话: **Python↔C 的边界从"每格一次"变成"每个 sheet 一次"**。

**融合循环(bind_cells 整体替换)。** 原版 `bind_cells` → `parser.parse()` → `parse_row()` → `parse_cell()` 是四层 Python 调用, 中间用 dict 传值。加速版把四层全部内联进一个 Cython 编译的 C 循环:

```text
iterparse 流水线里:
  行标签到达 → 行计数/行维度副作用(逐行复刻原版)
  每个格元素 → 单遍扫描子元素(v/f/is 一轮拿全, 替代 3 次子树查找)
             → 坐标单遍解析(无切片/反转/字典)
             → Cell.__new__ 直填 7 个槽位
             → ws._cells[(row, col)] = cell
```

效果: 每格的**中间 dict 消失**(值直接走 C 局部变量)、**4 层方法调用消失**(循环体内是编译后的机器码)、**子树扫描从 3 遍变 1 遍**。

**GC 守卫(单项 -3.9s)。** 加载期间堆上持续增长到几百万个长命且无环的对象, 但 CPython 的循环 GC 每分配 700 个对象(gen0 阈值)就醒来把它们全部扫一遍——几乎收不到垃圾, 纯浪费。融合循环入口 `gc.disable()`、出口恢复, refcount 回收完全不受影响。

**语义等价(不是简化, 是搬运)。** 融合循环逐行复刻 openpyxl 3.1.5 的行为: date 格式的数值转换、共享字符串查找、inlineStr、公式判断、行维度副作用……全部调用 openpyxl 自己的同一批辅助函数。产物是原汁原味的 `openpyxl.cell.Cell`(`type(ws["A1"]) is Cell`)。

### 2.3 替换机制: 同名方法替换, 不改任何调用方

```text
load_workbook                        (stock, 不动)
→ ExcelReader.read_worksheets        (stock, 不动)
→ WorksheetReader.bind_all           (stock, 不动)
→ self.bind_cells()                  ★ 唯一被替换的方法
→ bind_merged_cells / bind_hyperlinks / bind_formatting ...   (stock, 不动)
```

`WorksheetReader.bind_cells` 这个类属性被指向 Cython 融合循环。openpyxl 在 `bind_all()` 里调 `self.bind_cells()` 时, 属性查找命中的就是编译版——openpyxl 其余代码零感知。融合循环拿到同一个 `self`(同一个 WorksheetReader), 输入与原版完全一致(`parser.source` zip 流 / `shared_strings` / `date_formats` / `ws._cells`), 不需要任何新数据通道; 跑完后 `ws._cells` 里是原生 Cell, `parser` 上的结构状态按原版副作用一一就位, 后续 stock 阶段读起来毫无差别。

另有一处同类替换: `WorkSheetParser.parse_cell` 也换成编译版——它服务 **read_only 流式路径**(这条路径不经 bind_cells, 单独受益)。

**注入链**: 容器里 `python3` 启动 → site-packages 的 `oxlspeed.pth` → bootstrap 注册 lazy meta_path finder 后退出(不 import openpyxl, 不用 openpyxl 的进程零开销) → 任何代码首次 `import openpyxl` 的瞬间, 真实代码正常加载执行完毕 → 立刻完成方法替换。

### 2.4 安全防线

- bootstrap 版本门: `openpyxl != "3.1.5"` 一律不启用, 回退 stock(融合循环是 3.1.5 内部语义的逐行移植);
- `OPENPYXL_SPEEDUPS=0` 运行时一键关闭;
- StyleArray 逐格拷贝保留: openpyxl 的样式描述符是原地修改 `cell._style`, 若各格共享样式表条目, 改一个格子的字体会波及全表同样式格子——拷贝是正确性必需;
- GC 守卫准确语义: gc 是进程全局状态, 当前单线程 openpyxl 工作流下语义不变(已验证), 若宿主进程内有其他线程同时制造循环引用会改变 GC 触发时机, 属已知边界;
- patch/执行中任何异常 → 吞掉, 继续 stock, 业务不中断。

### 2.5 为什么它"通用"

它**不识别任何文件/Sheet/结构**——任何工作簿、任何 XLSX 流程, 只要走 `load_workbook`, 每格都经过同一条编译路径。收益随 Cell 数线性放大: 250 万格 = 冷加载 -25%; 小表收益小但绝不变慢。

## 三、实测(发行版 CPython 容器)

### 微基准(123.5MB / 12.3 万行 / 250 万格工作簿)

| 操作 | stock | 优化后 | 降幅 |
|------|----:|----:|----:|
| 全量冷加载 | 22.27s | **17.91s** | **-19.6%** |
| LibreOffice 重算形态加载(共享字符串) | 16.2s | **14.33s** | **-11.5%** |

归因: 冷加载中解析期 GC 守卫单项约 -3.9s, 其余为融合直建循环; 存盘走原生 stock 路径, 无扰动(26.6s ≈ stock 25.5s, 噪声内)。

### 端到端(同日同窗口 A/B, fixed 单任务)

| 指标 | stock | speedups | Δ |
|------|----:|----:|----:|
| Avg Latency | 258.3s | **217.9s** | **-15.4%** |
| Success Rate | 100% | 100% | — |

逐调用(对照此前的 stock 计时):

| 调用 | 内容 | stock | speedups | 降幅 |
|------|------|----:|----:|----:|
| TP-04 | 结构检查(冷加载) | 29.5s | 24.2s | -18% |
| TP-05 | 图表检查(冷加载) | 25.3s | 19.8s | -22% |
| TP-07 | 增强存盘 | 51.3s | 45.8s | -11% |
| TP-08 | 重算+双读 | 62.7s | 54.6s | -13% |
| TP-09/10 | 读公式/读值 | 20.9/20.5s | 16.9/16.9s | -19% |
| TP-13 | 业务校验 | 24.6s | 20.7s | -16% |
| TP-14 | 汇总特征 | 20.5s | 16.5s | -19% |

含 LibreOffice 的 TP-08 降幅来自该步骤中 soffice 前后的 openpyxl Python 处理; 存盘重的 TP-07 降幅里 load 侧贡献为主, save 侧走 stock 路径不变。

### 正确性(逐格指纹, 非抽样)

250 万格的(坐标/值/类型/样式/批注/超链接)指纹, 扩展开启 vs 关闭(`OPENPYXL_SPEEDUPS=0`)对照:

| 场景 | md5 |
|------|-----|
| 模板全量 | 一致 ✓ |
| LibreOffice 重算形态(共享字符串) | 一致 ✓ |
| load→save→load 往返 | 一致 ✓ |

## 四、证伪方向(有数据, 不再投入)

| 方向 | 结论 | 依据 |
|------|------|------|
| zlib-ng(zlib-compat 预加载) | 持平 | python/LibreOffice 全兼容但加载/存盘均在噪声内; 该工作簿压缩层全程仅 ~1s 占比 |
| CPU 绑核(cpuset 替代 CFS 配额) | 持平 | cgroup `nr_throttled=0` 无限流; Python 侧与 LibreOffice 侧均无差异 |
| LibreOffice 并发参数 | 持平 | MAX_CONCURRENCY 1/2/4 AB 无差异(工作簿仅 36 公式, Calc 无从并行); governor 已是 performance |
| 换 XML 解析器(Element→更重的 C 节点实现) | 慢 59% | 此前实验: 25.8→41.1s, 方向反了 |

## 五、剩余瓶颈与下一步

| 项 | 耗时 | 性质 |
|----|----:|------|
| LibreOffice 重算 | ~16s | 负载本身(soffice 读入 123MB+重算+写出) |
| 存盘写路径 | ~25s | 250 万格 XML 序列化+压缩, 原生 stock 路径 |
| 每格 C-API 硬成本 | ~7s | Cell 分配/槽位/拷贝/字典; 地板 = iterparse 7.6s + 模型转换 |

**下一步优先级**(按收益/风险比): ① writer 侧融合 speedups(Cell→et_xmlfile 原生循环, save 是当前最大单项); ② reader 再下沉 native SAX→Cell(攻 7.6s 地板, 工程风险较高); ③ 兼容性 corpus 扩充。zlib/NUMA/绑核/SVE 等外围方向不再投入。

## 六、文件与复现

| 文件 | 作用 |
|------|------|
| `patches/oxlspeed/openpyxl_speedups.pyx` | Cython 加速源(coordinate/parse_cell/融合 bind_cells + GC 守卫) |
| `patches/oxlspeed/oxlspeed_bootstrap.py` | 懒加载注入钩子(版本门 3.1.5, 失败回退 stock) |
| `patches/oxlspeed/oxlspeed.pth` | .pth 注入 |
| `patches/oxlspeed/build.sh` | 扩展编译 + 镜像构建 |

```bash
# 扩展编译(宿主需 cython 与目标 python3.12 头文件), 镜像 = 基础镜像 + 上述三文件
bash patches/oxlspeed/build.sh
bench-core --provider docker --config config/common/document-xlsx-speedups.yaml -n 1
```

环境开关: `OPENPYXL_SPEEDUPS=0`(关闭扩展, 完全回退 stock 行为)。
