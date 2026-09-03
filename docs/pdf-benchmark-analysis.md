# PDF 文档基准性能分析报告

> 基准: OF-306 联邦就业申请表批量填充 (10 申请人 × 3 页 PDF)
> 环境: 蓝区 920B 服务器 (ARM aarch64), 2核4G 容器, pypdf + Poppler/Pillow 软件栈
> 数据来源: `[CALLTIMINGS]` 埋点日志 / cProfile / LD_PRELOAD 探针 (libzcount.so)

## 一、调用链

### 1.1 外层框架说明

外层(`run_benchmark` / `RoundRobinTaskManager` / `DocumentRoundRunner` / `StatsCollector` / 配方加载等)只是 **bench-core 的框架外壳**——一个模拟 agent 按固定剧本回放工具调用、外加评测仪表,用于造可复现负载。**无需关心它的时间**,真 agent 接进来这层会整体替换。本报告只聚焦里面真实 agent 会走的 **21 次工具调用**。

> 前置(外壳做的,不计入 21):`prepare_workspace` 把种子 `cp -a /opt/document-bench/pdf → <WS>` 并建 `output/`,使每次任务起点一致。
> `<WS>` = `/root/.openclaw/workspace/tool-modeling/SUB-MEM-PDF-01`(容器内工作区)。

### 1.2 21次工具调用

#### P01 inspect_prepare — 检查与准备

| # | 函数 | 执行命令 | 做什么 |
|---|------|---------|--------|
| 1-7 | read | `SKILL.md` / `forms.md` / `verify_pdf_batch.py` / 4 个 skills 脚本 | 读取技能文档与脚本源码 |
| 8 | exec | `mkdir -p output/rendered/template output/field_values output/filled` | 建输出目录 |
| 9 | exec | `check_fillable_fields.py of306.pdf > check.log` | `pypdf` 检查表单可填充性 |
| 10 | exec | `cat check_fillable_fields.log` | 查看检查结果 |
| 11 | exec | `extract_form_field_info.py of306.pdf form_field_info.json` | `pypdf` 提取 38 个表单字段 |
| 12 | read | `form_field_info.json` | 读字段清单 |
| 13 | exec | `convert_pdf_to_images.py of306.pdf rendered/template/` | `pdftoppm` 渲染 3 页模板 PNG |

#### P02 build — 构建数据

| # | 函数 | 执行命令 | 做什么 |
|---|------|---------|--------|
| 14 | write | base64 heredoc 写 `generate_and_run_batch.py` | 写生成脚本 |
| 15 | exec | `python3 generate_and_run_batch.py` | 生成 10 份申请数据 JSON |
| 16 | exec | `python3 -c "validate field IDs..."` | 校验字段 ID 合法性 |
| 17 | write | base64 heredoc 写 `run_batch_fill_render.py` | 写批量处理脚本 |

#### P03 process_publish — 批量填充与渲染(最重)

| # | 函数 | 执行命令 | 做什么 |
|---|------|---------|--------|
| 18 | exec | `python3 run_batch_fill_render.py` | **10 次填充 + 10 次渲染交替执行** |
| 19 | write | `batch_summary.json` (固定内容) | 写批次摘要 |

#### P04 verify_deliver — 校验与交付

| # | 函数 | 执行命令 | 做什么 |
|---|------|---------|--------|
| 20 | exec | `verify_pdf_batch.py` (10 PDF 字段 + 像素差异) | `pypdf`+`PIL` 业务验收 |
| 21 | exec | `find + wc -l + ls` | 交付物统计 |

## 二、测试点说明

测试点 = 上面工具调用链路里的 21 次调用,每次调用即一个测试点。外层框架不计。

## 三、各阶段耗时

### e2e耗时

#### 21 个测试点实测

| TP | 阶段 | 函数 | 耗时 | 占比 | 操作描述 |
|----|------|-----|-----:|----:|---------|
| TP-01~07 | P01 | read×7 | 各~53ms | 3.1% | 读文档/脚本 (exec 通信开销) |
| TP-08 | P01 | exec | 0.053s | 0.4% | `mkdir` 建目录 |
| TP-09 | P01 | exec | 0.229s | 1.9% | `pypdf` 可填充检查 |
| TP-10 | P01 | exec | 0.090s | 0.8% | `cat` 检查结果 |
| TP-11 | P01 | exec | 0.232s | 1.9% | `pypdf` 提取字段 |
| TP-12 | P01 | read | 0.090s | 0.8% | 读字段 JSON |
| TP-13 | P01 | exec | 0.543s | 4.5% | `pdftoppm` 渲染模板 + PIL PNG 压缩 |
| TP-14 | P02 | write | 0.165s | 1.4% | 写生成脚本 |
| TP-15 | P02 | exec | 0.082s | 0.7% | 生成 10 JSON |
| TP-16 | P02 | exec | 0.100s | 0.8% | 校验字段 ID |
| TP-17 | P02 | write | 0.154s | 1.3% | 写批量脚本 |
| **TP-18** | **P03** | **exec** | **8.354s** | **69.6%** | **10 填充 + 10 渲染 (见下方拆解)** |
| TP-19 | P03 | write | 0.160s | 1.3% | 写批次摘要 |
| TP-20 | P04 | exec | 0.944s | 7.9% | 业务验收 (10× pypdf 字段 + 10× PIL 像素比对) |
| TP-21 | P04 | exec | 0.115s | 1.0% | 交付物统计 |

#### 阶段小计

| 阶段 | 耗时 | 占比 |
|------|-----:|-----:|
| P01 inspect_prepare | 1,680ms | 14.0% |
| P02 build | 515ms | 4.3% |
| P03 process_publish | 8,528ms | **71.1%** |
| P04 verify_deliver | 1,074ms | 9.0% |
| 外层开销 (prepare_workspace 工作区复位 + 终态校验, 见 task_runner/document.py) | ~200ms | ~1.7% |
| **总计** | **11.997s** | 100% |

> 基线口径: 11.997s 为本节测量基线 (旧窗口)。第四节 A/B 采用同窗对照另测, 两口径不混用。

#### TP-18 内部拆解 (10×fill + 10×render 交替, 各 20 次 `subprocess.run`)

| 子步 | fill (s) | render (s) | 累计 (s) |
|------|------:|------:|------:|
| 每申请人 (×10, 方差<1%) | 0.331 | 0.489 | — |
| **合计** | **3.317** | **4.891** | **8.208** |

fill 单次 (0.33s, 子进程 wall): 解释器启动+导入 ~0.11s + pypdf 库操作 ~0.22s (拆解见"pypdf 热点分析")。

render 单次拆解 (重测, 同一次运行内顺序计时, 原始数据见 `docs/data/pdf-analysis/render-breakdown.txt`):

| 环节 | 耗时 | 说明 |
|------|-----:|------|
| `pdftoppm -r 200` 渲染 3 页 | ~153ms | 原生渲染 |
| PIL 加载 3 页 PPM | ~16ms | |
| PIL 保存 3 页 PNG (cl=6) | **~453ms** | **大头: zlib 压缩** |
| **render 合计 (standalone 重测)** | **~622ms** | bench 内均值 ~0.49s (页缓存更热) |

即 render 的大头确认为 **PNG 压缩 (~0.45s/次, 底层 zlib)**——这是"为什么要分析 zlib"的直接依据。

### 瓶颈定位: 为什么分析 zlib

热点不是拍脑袋选的, 而是沿耗时占比逐层下钻的结果:

```text
E2E 12.0s
 └─ P03 占 71% (8.5s)                       ← 阶段小计直接指出
     └─ TP-18 占 69.6% (8.35s)              ← 测试点表指出
         ├─ render ×10 = 4.89s              ← TP-18 内部拆解
         │    └─ PNG 保存 ~0.45s/次         ← render 单次拆解: 压缩是大头
         │         └─ 底层是 zlib (原生 C 库)
         └─ fill ×10 = 3.32s
              └─ clone 0.11s + write 0.03s  ← fill 单次内部
                   └─ 底层是 pypdf (纯 Python)
```

TP-18 下钻后负载分成性质不同的两条线:

| 线 | 软件 | 性质 | 现成工具 |
|----|------|------|---------|
| Python 线 | pypdf (clone/write/get_fields) | 解释器执行字节码 | cProfile (拿函数级热点) |
| 原生线 | zlib (PNG 压缩/PDF 流) + pdftoppm (渲染) | C/C++ 库 | **cProfile 不可见**——只显示一个 `save` 总耗时, 内部黑盒 |

Python 线用 cProfile 直接拆 (见下节); 原生线的黑盒需要专门工具——因此自研 `libzcount.so` 探针 (LD_PRELOAD 拦截 zlib 入口, 精确计数+计时), 用来回答"原生线的 1.5s 里 zlib 占多少、值不值得优化"。pdftoppm 同为原生但先前微基准已确认无优化空间 (见 4.3), 不再展开。

### zlib 热点分析

> 被测: 真实基准全流程, `libzcount.so` 探针 (LD_PRELOAD 拦截 deflate/inflate, 精确计数+计时, 日志按 pid+starttime 命名防容器 pid 复用覆盖)。

#### 探针实测 (单任务)

| 指标 | 值 | 解读 |
|------|-----:|------|
| deflate 调用 | 33,048 次 / **1,326ms** | 全部为 Pillow PNG 编码的流式小块调用 (单次 40.1µs) |
| inflate 调用 | 20,347 次 / **139ms** | 来自 pypdf 读侧解压与 P04 的 PIL PNG 解码 (见下方说明; pdftoppm 的用量探针不可见, 尚未精确分摊) |
| **zlib 合计** | **1,465ms** | **占 E2E 12.3%** — 原生层第一大热点 |

调用特征: 每页 PNG 约 1,000 次 KB 级小块喂给 zlib (Pillow 流式编码), 非一次性大块——这类高频小块调用场景下, 向量化实现相对逐字节实现的收益被放大。

**"内嵌流"是什么**: PDF 文件里不是所有内容都明文存放——为了省体积, 页面内容、字体、表单外观等对象以 FlateDecode **压缩形式**内嵌在文件里, 解析时必须先解压 (inflate) 才能读到内容。实测该模板含 **18 个压缩对象**, 一条流要分多次小块喂给 inflate 才能解完。PDF 全流程被打开 23 次 (P01 脚本 2 次 + P03 fill 10 次 + P04 验收: 模板 1 次 + 输出 PDF 10 次)。另经实测验证: **pypdf 写出侧零 deflate** (输出时模板流原样搬运, 不重新压缩), 压缩开销集中在 render 的 PNG 编码。

inflate 的 139ms 由多个消费者构成: pypdf 读侧解压 + P04 验收时 PIL 打开 PNG 做像素比对 (`verify_pdf_batch.py` 的 `changed_pixel_count` 用 `Image.open` 解码模板/输出 PNG) + pdftoppm (其 zlib 调用绕过探针, 不可见)。**未做逐消费者精确分摊**; 因总量仅 139ms, 分摊不影响任何结论。

1,465ms 的具体去处 (对应回测试点; 原始逐进程探针日志见 `docs/data/pdf-analysis/zexact_*.txt`):

| 去处 | 操作 | zlib 耗时 | 对应测试点 |
|------|------|--------:|-----------|
| **PNG 编码** (33 页 × cl=6 流式压缩) | PIL `image.save` → deflate | **~1,326ms** | TP-13 + TP-18 内 render×10 |
| 解压 (读侧, 多消费者) | pypdf 读 PDF 流 + P04 的 PIL PNG 解码 | **~139ms** | TP-09/11/18/20 |
| **合计** | | **1,465ms (12.3%)** | |

**deflate 九成发生在 render 的 PNG 压缩**——优化 zlib 的预期收益将主要落在 P03, 与后文 4.1 的实测 (P03 -775ms) 相互印证。

### pypdf 热点分析

> 被测: 容器内对真实模板执行**一次完整 fill** (`PdfReader` 打开 → `PdfWriter(clone_from=...)` → 填字段 → `write` 输出), cProfile 采样, 7 次取中位。
> 单次 fill 全程 **221ms**, 其中业务操作 (写入字段值) 仅 **~3ms——98% 以上是 pypdf 库自身开销**, 与 zlib 段口径一致: 优化对象是库, 不是业务。
> 口径说明: 微基准填 23 个终端字段 (实际配方每申请人填 18 个, 见 `pdf_key_operations.json`); 业务写入耗时与字段数近似线性, 该差异 (~ms 级) 不影响结论。
> 原始数据: `docs/data/pdf-analysis/cprofile-fill-221ms.txt`。
> **注意: cProfile 插桩使绝对耗时放大约 3.3 倍 (profile 总计 0.725s vs 无插桩 wall 221ms), 下表毫秒值仅供同表内相对比较, 占比按 top-16 自身耗时合计 (0.414s) 归一。**

#### cProfile 热点函数 top 10 (按自身耗时降序)

| # | 帧 | tottime | 调用数 | 占 top-16 |
|---|----|------:|------:|----:|
| 1 | `read_object` (递归解析) | 52ms | 32,531 | 12.6% |
| 2 | `read_until_regex` (词法扫描) | 52ms | 29,111 | 12.6% |
| 3 | `DictionaryObject.read_from_stream` | 36ms | 907 | 8.7% |
| 4 | `typing.__instancecheck__` | 36ms | 64,264 | 8.7% |
| 5 | `BytesIO.read` | 33ms | 220,865 | 8.0% |
| 6 | `_reference_clone` (拷贝簿记) | 28ms | 24,866 | 6.8% |
| 7 | `renumber` (写出侧重编号) | 24ms | 7,771 | 5.8% |
| 8 | `BytesIO.seek` | 24ms | 145,649 | 5.8% |
| 9 | `isinstance` (内建) | 22ms | 78,800 | 5.3% |
| 10 | `clone` 分派器 | 21ms | 900 | 5.1% |

#### 按性质归类 (占 top-16 自身耗时)

| 归类 | 涉及函数 | 占比 | 说明 |
|------|---------|----:|------|
| **PDF 对象惰性解析** | `read_object` + `read_until_regex` + 各 `read_from_stream` + `BytesIO` + `__new__`/`append` | **~62%** | clone 触发 888 个 PDF 对象从字节流全量解析——纯 Python 递归下降 + 正则 tokenizer, 外加几十万次微小流读取 |
| **运行时类型检查税** | `typing.__instancecheck__` + `isinstance` | **~14%** | pypdf 核心类误继承 Protocol 元类, 每次类型判断走慢速协议核对 (4.2 优化点直接对症) |
| **真正的拷贝簿记** | `_reference_clone` + `clone` 分派 | **~16%** | 名为"深拷贝"的部分 |
| **写出序列化** | `renumber/unnumber` + `write_to_stream` 族 | ~10% | 输出时逐对象重算引用编号并序列化 |

**结论: "clone 慢"名不副实——六成在解析、一成半在类型检查, 真正的拷贝簿记与序列化各占一小块。** 单次 221ms 的 fill 在 P03 重复 10 次, 加上 P01/P04 的读取, **含进程启动与导入在内 pypdf 相关开销上界约 3.5s** (库自身耗时未与启动/导入完全分离); 与 zlib 的 12.3% 并列两大优化对象。

## 四、优化点尝试

### 4.1 系统压缩库替换 zlib-ng

#### 背景

PDF 文档基准(2核4G 容器, 单任务)优化前端到端 **11.997s**。探针归因显示 zlib 原生层占 **12.3%**(1,465ms/任务): 系统自带 zlib 诞生于上世纪 90 年代, 关键热点路径 (最长匹配查找、逐块比对) 为逐字节标量实现 (CRC32 已有 ARM 指令路径, 但不涉及本负载的热点), 未利用 ARM 芯片的 NEON 向量指令。而本负载的 PNG 编码是流式小块调用 (33,048 次 deflate), 恰是向量化的理想场景。

#### 方案

源码编译 **zlib-ng 2.2.4**(zlib 的现代化替代实现, `zlib-compat` 兼容模式——同名 `libz.so.1`、同一套导出符号, 上层软件零感知), 编译参数 `-O3 -mcpu=tsv110`。注: 实测本机 CPU 为 HiSilicon part 0xd02, GCC 无对应调优名, tsv110 为最接近的已知核; 该调优项对收益的贡献未单独验证 (收益主体来自 NEON 向量化实现本身)。其 ARM NEON 向量化覆盖压缩的四个热点环节:

1. **匹配比对 (compare256)**: 原版逐字节比较 → NEON 一次加载 16 字节整块比对, 异或后用 CTZ 类指令定位首个差异字节, 显著减少每字节的循环迭代 (图像大片相同颜色场景收益最大);
2. **哈希表平移 (slide_hash)**: 逐项 16 位减法 → 饱和减法一次处理 64 个表项;
3. **块填充 (chunkset)**: 逐字节复制 → 128 位寄存器查表排列一次铺 16 字节;
4. **校验和 (adler32)**: 串行双累加 → 4 路向量累加器拆依赖链。

部署: 编译产物置于 `/opt/zlib-ng`, 容器级 `ENV LD_PRELOAD` 全局生效 (不覆盖发行版文件, 删一个环境变量即回退)。曾抓到部署坑: 最初放 `/usr/local/lib` 期望链接器优先——实测未生效 (进程仍加载系统 zlib, E2E 假持平); 修正后所有镜像构建期带"进程内实际加载路径"断言。

#### 实测

##### 端到端 (METHOD.md 标准流程, 同窗 A/B, 各 15 任务, Success 100%; 原始日志 `docs/data/pdf-analysis/e2e_*.log`)

| 指标 | stock (系统 zlib) | zlib-ng | Δ |
|------|----:|----:|----:|
| P01 inspect_prepare | 1,881ms | 1,688ms | -193ms |
| P02 build | 606ms | 571ms | -35ms |
| P03 process_publish | 8,695ms | 7,920ms | **-775ms** |
| P04 verify_deliver | 1,097ms | 1,045ms | -52ms |
| **Avg Latency** | **12.28s** | **11.22s** | **-1.06s (-8.63%)** |

##### 探针归因 (同探针同负载 A/B; 调用次数基本一致: deflate 33,048 vs 33,056, 差 8 次 ≈0.02%, 因变体间编码器分块边界略有差异)

| 指标 | 系统 zlib | zlib-ng | Δ |
|------|----:|----:|----:|
| deflate | 1,326ms / 33,048 次 | 568ms / 33,056 次 | **-57%** (单次 40.1→17.2µs) |
| inflate | 139ms / 20,347 次 | 53ms / 20,347 次 | **-62%** |
| **zlib 合计** | **1,465ms (12.3%)** | **620ms (5.6%)** | **-58%** |

zlib 内部节省 845ms 约占 E2E 节省 1.06s 的 80%, 两个口径 (探针计时的库内耗时 vs 端到端 wall) 方向一致、数量级吻合。正确性: PNG 字节流不同 (压缩路径变了) 但**解码像素逐位一致**, P04 逐像素校验 100% 通过 (15/15 任务)。

##### 火焰图对比 (优化前后, `docs/data/pdf-analysis/flamegraph/`)

对同一 workload (复刻 P03: 10× fill + 10× render ×3 轮) 用 py-spy 99Hz native 采样, 优化前后各一份 (原始数据与生成脚本见同目录):

| 指标 | 系统 zlib | zlib-ng | 变化 |
|------|----------:|--------:|-----:|
| Python 侧总样本 | 2,080 | 1,577 | -24.2% |
| zlib 帧样本 | **948 (45.6%)** | **477 (30.2%)** | **-49.7%** |
| fill 路径样本 (未优化对照) | 605 | 638 | 持平 (噪声内) |

- **`png-zlib-before.svg` vs `png-zlib-after.svg`** (主对比): 只截取 PNG 编码→zlib 路径, 跳过未优化路径。优化前 libz 是火焰图中 `_encode_tile` 下方的整块大框 (符号剥离不可细分); 优化后同位置缩水约一半, 且 `deflate_medium` / `longest_match_neon` 等内部函数名可见。
- **`flame-diff.svg`**: 差分图, zlib 叶帧 -29.7% (纯蓝); fill 侧 (pypdf 读/克隆) 两侧持平, 证明收益全部来自 zlib 替换。
- `flame-full-before/after.svg`: 全景 (含 fill 路径上下文)。

**读图分析**:

1. **优化前 (`png-zlib-before.svg`)**: PNG 编码路径 1,443 样本中 libz 占 945 (**65%**), Pillow 胶水 (逐 tile 的 `_encode_tile` 调度与编码回调) 占 34%。libz 内部因发行版剥离符号呈单一暗块 (`libz内部(符号剥离)`) 无法细分——只有自编译的 zlib-ng 才能看清内部结构。
2. **优化后 (`png-zlib-after.svg`)**: libz 缩至 475 样本 (**-50%**), 内部结构可见 (按含该帧的样本计数, 嵌套计): 主压缩循环 `deflate_medium` 贯穿 ~100% 的 zlib 样本, 其中 **~40% 位于 NEON 向量化的最长匹配 `longest_match_neon`**, **~34% 位于哈希插入 `insert_string`/`quick_insert_string`**, 其余为 `zng_tr_flush_block`/`compress_block`/`fill_window`/`slide_hash_neon` 等落盘与簿记。收益落点与本节机制解释吻合: 匹配查找向量化 + 哈希管理现代化。
3. **差分 (`flame-diff.svg`)**: 唯一大蓝块是 zlib 叶帧; 全部红帧 ≤ +0.95% (pypdf fill 侧 605→638, 采样噪声量级)。单变量替换 (只换 libz) 下, 时间减少精确发生在被替换的库内, 未触碰路径零回归、无新增开销——E2E 收益的因果链闭合。
4. **交叉验证**: 火焰图口径 zlib -49.7% vs zcount 探针口径 deflate 内部 -57% (1,326→568ms), 两种独立测量 (采样 vs 拦截计时) 方向与量级一致。
5. **剩余天花板**: 优化后 PNG 路径中 Pillow 胶水占 47% (428/906) 已反超 libz (52%)——该路径继续提速需改动 Pillow 编码调度 (超出零侵入约束), libz 侧余量已小。

### 4.2 pypdf 协议继承移除

#### 背景

cProfile 热点第 2 名: 每次 clone 执行 **62,676 次 `typing._ProtocolMeta.__instancecheck__`**, 占 clone 耗时 11%。根因: pypdf 的 `PdfObject` 与 `XmpInformation` 两个核心类出于类型标注目的继承了 `typing.Protocol` 基类——该机制本应只供开发工具静态分析, 运行时继承让每一次 isinstance 都走一遍复杂的协议核对流程 (实测纯 isinstance 慢 5.8 倍), 属于纯"运行时税"。

#### 方案

去掉两处运行时 Protocol 继承 (共 **2 行** sed 改动, 类型标注不受影响——Protocol 是结构化类型, 具体类无需继承)。此修复对使用 pypdf 的一切场景 (合并、加水印、旋转、拆分) 通用, 具备回馈 upstream 条件。

#### 实测

| 指标 | stock | 补丁后 | Δ |
|------|----:|----:|----:|
| 单次 clone | 186.4ms | 159.5ms | **-14.4%** |
| 与 zlib-ng 叠加 E2E | 11.18s | **10.96s** | -0.22s |

正确性: 冻结业务脚本 (`fill_fillable_fields.py`) 输出与补丁前 **md5 逐字节一致**。

### 4.3 未成功的探索

| 探索 | 结果 | 原因分析 |
|------|------|---------|
| SVE 向量化 (手写热点函数 SVE 版, 20 万用例交叉验证后集成 zlib-ng) | 真实 E2E **零收益** (11.12 vs 11.00s) | 孤立微基准 1.8× 但函数在整流程占比小; 本机 256-bit SVE 疑 2×128 拆分执行 |
| 中间图片放内存盘 (/dev/shm) | 零收益 | 文件本就命中页缓存, I/O 不是瓶颈 |
| pypdf 增量写入模式 | **反慢 18%** | 读库源码: 其"增量模式"初始化仍复制全部 1,820 对象并逐个算指纹 (比纯拷贝还重), 为"安全追加"设计非为性能 |
| pypdf Cython 编译 (全包/叶模块) | 语义 bug / 零收益 | 全包: 编译改变元类/布局, 读真实模板即报错; 叶模块: 热点本在 C 层。结论: 自动编译不可行, native 化须走窄接口 C 扩展 |

## 五、结论与下一步

1. **通用约束下 (只动底层库与 CPU 层, 零 workflow 侵入)**: 同窗 A/B 实测 **12.28 → 11.22s (-8.63%)**, 唯一有效项 = zlib-ng 系统压缩库替换 (旧窗口基线 11.997s 与本 A/B 不混用); pypdf 协议补丁单独实测另提供 -0.22s (11.18→10.96s), 已归档 (维护成本高于收益)。
2. **排雷结论**: SVE (当前硬件)、/dev/shm、增量写入、Cython 自动编译四条路线全部以严格 A/B 关闭, 避免后续在死路投入。
3. **下一步已论证的空间**: pypdf 解析/序列化的窄接口 C 扩展下沉 (cProfile 已完整定义规格: `read_object` 词法循环 + 62K isinstance + 358K 次 BytesIO 微调用), 阶段目标 clone 176→100~130ms; 串行 fill/render 结构成本在通用约束下不可回收。
