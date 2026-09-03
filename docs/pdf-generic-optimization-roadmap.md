# PDF 通用底层优化路线（v2 决议 + 基线重建）

> 日期: 2026-08-31（同日完成路线表全部条目实验）
> 决议背景: 用户判定 workflow-aware 注入优化（进程合并/跨调用缓存/流水线/脚本拦截）会改变原流程行为、影响未来新流程，**后续只做底层库 + CPU 层面的通用优化**。

## 一、双轨道制

| 轨道 | baseline | 状态 |
|------|---------|------|
| **A. workflow-aware**（历史四轮优化） | 11.96s → 5.42s (-54.7%) | **归档为极限性能参考**, 不再演进; 产物 = `ubuntu-document-bench:pdf-opt` 镜像 + `patches/pdf_accel.py` + `docs/pdf-optimization-report.md` |
| **B. 通用底层**（本路线） | **11.98s** | **现役主线**; 本轮全条目实验完毕（见 §4 总表） |

轨道 B 允许的手段: CPython 构建 / pypdf / Pillow / Poppler / libpng·zlib / FreeType / 编译选项 / libc·分配器 / 内核·绑核·NUMA·频率。
明确禁止: 识别脚本名、monkey patch subprocess、跨进程复用对象、按 applicant 数建流水线、按模板做 cache、改 helper 调用顺序、对 OF-306 写专用 fast path。

## 二、通用 baseline（无注入基础镜像, 08-31 复测）

| 阶段 | 复测 | 原始 (08-29) |
|------|-------:|-------:|
| P01-inspect_prepare | 1,738ms | ~1,680ms |
| P02-build | 558ms | ~515ms |
| P03-process_publish | 8,592ms | 8,528ms |
| P04-verify_deliver | 1,092ms | 1,074ms |
| **合计** | **11.98s** | 11.96s (100% 成功) |

## 三、pypdf 基础设施成本解剖（vanilla 容器 cProfile 实测）

单次 `PdfWriter(clone_from=...)` 176ms + `write` 33ms; 业务操作（填字段）仅 3.3ms/份 = **1.5%**, 98.5% 是库基础设施。10 份 ≈ 2.15s (P03 的 25%)。

clone 176ms 构成:

| 帧 | 调用数 | 占比 | 性质 |
|----|-------:|-------:|------|
| `read_object` 递归解析 | 32,427 | 64% | clone 触发 888 对象全量惰性解析 (纯 Python 递归下降 + 正则 tokenizer) |
| `typing._ProtocolMeta.__instancecheck__` | 62,676 | 11% | `StreamObject`/`PdfObject`/`NullObject` 定义为 runtime_checkable Protocol, 全部 isinstance 走慢速协议检查 |
| `BytesIO.read/seek` | 358,486 | 10% | 字节流随机访问 (C 层) |
| `_reference_clone` | 24,866 | 5% | 真正的拷贝簿记 |

write 33ms: `renumber` 7.6k 次 + 87,548 次微写 + 65,284 次 str.encode —— 典型解释器指令量问题, 无单一大热点。

## 四、路线表全条目实验结果（08-31 完成）

| 优先级 | 条目 | 实验结果 | 判定 |
|:---:|------|---------|:---:|
| P0 | 通用 baseline | 11.98s 复现 | ✅ |
| P0 | pypdf clone 解剖 | 见 §3: 热点=解析(64%)非拷贝(5%) | ✅ |
| P0 | pypdf native accelerator PoC | 见 §5 三段: 全包 Cython 语义 bug 阻塞; 叶模块 Cython 无收益; Protocol-isinstance 记忆化 +5% | 🔶 |
| P1 | pypdf serializer native 化 | write 仅 25ms/份且与 clone 同属一个下沉工程, 不单独立项 | 🔶 并入 |
| P1 | pdftoppm perf/PMU 分解 | perf 被 `perf_event_paranoid=2`+sudo 密码阻挡 → 改用差值计时法完成 Poppler/zlib 判断 | ⚠️ 降级完成 |
| P1 | Kunpeng workload-PGO CPython | 源码 3.12.3 + `--enable-optimizations --with-lto` + 真实 PDF workload 训练集构建成功; clone+write 212.3 vs 209.4ms = **零收益**（与官方镜像实验互为印证: Ubuntu 系统 Python 已是优化构建） | ❌ 证伪 |
| P2 | Poppler `-mcpu=tsv110 -flto` | 源码 24.02.0 同版本自编, 输出**像素逐字节一致**; 单页 best-of-20: 85→82ms (**-3.5%, 噪声级**) — Ubuntu 官方 poppler 已充分优化 | ❌ 无收益 |
| P2 | zlib-ng 2.2.4 (zlib-compat, NEON) | 系统 libz 全局替换; 真实图像数据: compress cl=6 **-51%** / cl=1 **-56%**; PIL PNG save cl=6 **-36%** (40.0→25.5ms/页) / cl=1 -25%; PNG 字节流不同但**解码像素完全一致**(P04 逐像素校验可过); E2E 见 §6 | ✅ **唯一真实收益** |
| P2 | libjpeg-turbo / FreeType / libpng | 不在热路径: 渲染管线是 PPM(无 jpeg), PNG 编码走 PIL+libz(非 libpng), FreeType 在 poppler 内部由 Poppler A/B 覆盖 | ⏭️ 有据跳过 |
| P3 | cpuset 绑核 | clone 基准: 平均无差异, 但消除 +7% 离群抖动 (226.3→212.0ms); 纯尾延迟稳定性项, 默认不启用 | 🔶 稳定性 |
| ❌ | incremental=True / 官方 Python 镜像 / /dev/shm | 第五轮已证伪 | ❌ |

## 五、pypdf native 加速 PoC 详录（v2: 按外部评审修订执行顺序）

**Phase 0 已完成 —— pypdf 运行时 Protocol 继承移除（08-31 下午）**:

- 根因: `generic/_base.py:64 class PdfObject(PdfObjectProtocol)` 与 `xmp.py:193 class XmpInformation(XmpInformationProtocol, PdfObject)` 让具体类继承了 `typing._ProtocolMeta` 元类, 所有 isinstance 走慢速协议检查（62,676 次/clone）。Protocol 是结构化类型, 具体类无需继承。
- 修法: 两处去掉 Protocol 基类（sed 级, ~2 行, 不动 stdlib、不加缓存）。
- 实测: clone 186.4→159.5ms（**-14.4%**, 优于记忆化 -5%）; write 持平; 直接 API 与冻结 `fill_fillable_fields.py` 两条路径输出 **md5 逐字节一致**; isinstance 语义断言通过。
- 已并入 `pdf-generic` 镜像（构建期断言 metaclass=type）。

**后续阶段（按"serializer 先于 parser, clone 最后"重排）**:

| Phase | 内容 | 预期 | 依据 |
|:---:|------|------|------|
| A ✅ | Protocol 继承移除 | clone -14%（实测 -27ms） | 已完成 |
| B | `_speedups` serializer PoC（窄 C 扩展, 对象图→native 动态缓冲, 87,548 次微写合并为 ~千次 flush; byte-for-byte 回归可测） | write 25→10~15ms | 无 xref/容错/stream 语义, 最易做对 |
| C | native parser（`_speedups.read_object` 一次下沉到完整对象; bytes/BytesIO 走 buffer, 文件走 mmap, 其它流 fallback Python; 首版只支持 number/name/bool/null/array/dict/string/hex-string/ref 九类 token, stream/加密/repair 直接 fallback） | 第一阶段 clone 176→100~130ms; 进阶 60~90ms; <60ms 需 parser+对象构造+Protocol 全部下沉 | **目标而非上限**（64% 热点含 Python 对象构造, 不能全部被 C 消灭） |
| D | clone bookkeeping native 化 | 上限仅 ~5% | `_reference_clone` 实测占比小 |
| 架构原则 | 禁止整包 Cython 化（本轮已证语义偏移: `Trailer cannot be read`）; 原生路径缺失时 100% 回退原 Python 行为 | | |

**已关闭的死路**: 整包 Cython（54 模块编译成功但解析语义 bug, 排除 Protocol 元类/binding 指令后仍复现）; 叶模块 Cython（`_utils` 含 29k 次的 `read_until_regex`, 217 vs 209ms 无收益——热点成本本在 C 层 BytesIO/re, 编译 Python 包装层不改变本质）; stdlib Protocol-isinstance 记忆化（-5% 但改 stdlib 行为, 被 Phase A 的库内修法取代）。

## 六、通用镜像 v3 E2E（zlib-ng + pypdf 协议补丁）

`ubuntu-document-bench:pdf-generic` v3 = vanilla 基础镜像 + 两项通用优化:
1. **zlib-ng 2.2.4**（zlib-compat, `-O3 -mcpu=tsv110`）部署于 `/opt/zlib-ng`, 容器 `ENV LD_PRELOAD` 全局生效（v2 曾试 `/usr/local/lib` 软链——**未生效**; 后改 `/usr/lib` 同名硬替换可生效但覆盖发行版文件不利维护, v3 按 review 意见改为 `/opt`+LD_PRELOAD, 关闭只需删一个 ENV）
2. **pypdf 协议继承移除**（§5 Phase A）

同日 A/B（均 100% 成功）:

| | P01 | P02 | P03 | P04 | 合计 |
|---|---:|---:|---:|---:|---:|
| vanilla（同时段） | 1,847 | 637 | 8,622 | 1,128 | 12.23s |
| vanilla（上午） | 1,738 | 558 | 8,592 | 1,092 | 11.98s |
| v2 仅 zlib-ng | 1,719 | 554 | 7,896 | 1,008 | 11.18s |
| **v3 zlib-ng+协议补丁** | **1,697** | **577** | **7,658** | **1,030** | **10.96s** |

- vs 上午 vanilla 基线: **-8.5%**; vs 同时段 vanilla: **-10.4%**
- 贡献分解: zlib-ng ≈ -800ms（P03 压缩 + P01 渲染）, 协议补丁 ≈ -220ms（P03 内 10 次 clone × -27ms, 与微基准吻合）
- 像素/字节一致性: zlib-ng PNG 字节不同但解码像素一致（P04 逐像素 100% 过）; 协议补丁 fill 输出 md5 逐字节一致

## 六-2、图像编解码器 inventory（有据排除）

`pdfimages -list` 证实 OF-306 模板嵌入图全部为 32×32 原始 `image`/`smask`（无 `jpeg`/`jpx` 编码条目）→ **本 workload 无 DCTDecode 路径, libjpeg/libopenjpeg 确实不在热路径**（此前仅凭"输出是 PPM"推断不严谨, 现已实证）。FreeType: Poppler A/B 两版链接同一 system libfreetype, 该实验只证明"重编 Poppler 自身无收益", 未覆盖 FreeType 优化价值——按 ROI 暂缓, 理由改为"无独立证据", 不再写"不在热路径"。

## 七、结论

1. **通用轨道实现 11.98 → 10.96s（-8.5%）**, 两项贡献均纯库层、零 workflow 感知: zlib-ng 系统压缩库替换（-800ms）+ pypdf 协议继承移除（-220ms）。
2. 关闭的维度（全部有实测数据）: CPython 构建（官方镜像 + 自训 PGO 两次证伪）、Poppler 编译优化（-3.5% 噪声级）、tmpfs I/O、pypdf incremental、Cython 全包/叶模块、libjpeg/libopenjpeg（pdfimages 实证无 DCTDecode）。
3. 下一阶段排期（§5 表）: B 序列化器 `_speedups` PoC → C native parser（bytes/mmap 双快路径 + 九类 token + 完整回退）→ D clone 簿记。全部完成后的**阶段目标**: ~10.0~10.5s（parser 真实数据出来前不承诺更多）。
4. 对照 A 轨道 5.42s: 差距主体是 workflow 结构性成本（20 次进程冷启动/重复解析/串行 fill-render）, 通用约束下只能靠库内下沉合法回收 pypdf 部分。
5. **提交前必查**（review 指出）: 本地仓库 `config/common/document-pdf.yaml` 仍指 `pdf-opt`（A 轨道）, j 机已指 `pdf-generic`——正式提交时必须同步, 防止 benchmark 串轨; 两份 roadmap/round5 文档目前未追踪。
6. 产物清单（j 机）: `pdf-build:{base,pgo-python,native-libs,pypdf-cython,proto-patch}` 构建镜像、`ubuntu-document-bench:pdf-generic` v3 运行镜像、`~/pdfbuild/` 全部 Dockerfile。本轮全部工作未提交 git。

## 八、SVE 探索（08-31 追加, 应"既然都用 NEON 能否换 SVE"之问）

**硬件事实**: 该机"920B"实为 HiSilicon part 0xd02（非 tsv110）, 具备 SVE1, 实测 VL=256-bit; 但纯吞吐微基准显示 256-bit 仅 +8%（vs NEON 4×128 展开）——疑为 cracked 2×128 执行, 非 256 数据通路。无 SVE2。

**三函数孤立微基准**（NEON 为 zlib-ng 原实现, SVE 为手写, 均经正确性交叉验证: compare256 20 万随机用例、adler32 对标量参考 18 个边界长度、slide_hash memcmp）:

| 函数 | SVE/NEON | 说明 |
|------|--------:|------|
| compare256（匹配比对, 最热内循环） | **1.80x** | 256-bit 一次比对 + brkb/cntp 定位首个差异, 免去 NEON 版逐 8 字节 lane 检查 |
| slide_hash | 0.87x（更慢） | SVE1 无 u16 饱和减法, 需 cmp+sel+sub 三指令模拟 |
| adler32 | 0.85x（更慢） | cracked 256-bit 上水平加法更贵 |

**真实集成实验**: 把验证过的 SVE compare256 以 `#pragma GCC target("arch=armv8.2-a+sve")` + `getauxval(HWCAP_SVE)` 运行时探测集成进 zlib-ng（同 flags 双库对照, 反汇编确认 cntb/ld1b/brkb 指纹在最终 .so 中, 输出 md5 一致）。

**真实基准三变体对照**（修复探针 pid 复用漏采 bug 后, 同探针/同负载/3 任务精确计量, `libzcount.so` 计数+计时）:

| 指标 | 原版系统 zlib | zlib-ng (NEON) | zlib-ng (SVE) |
|------|------------:|--------------:|--------------:|
| deflate 耗时/任务 | 1,326ms / 33,048 次 | 568ms / 33,056 次 | 577ms / 33,056 次 |
| 单次 deflate | 40.1µs | 17.2µs | 17.5µs |
| inflate 耗时/任务 | 139ms / 20,347 次 | 53ms / 20,347 次 | 53ms / 20,347 次 |
| **zlib 合计/任务** | **1,465ms (E2E 的 12.3%)** | **620ms (5.6%)** | **630ms (5.7%)** |
| **端到端** | 11.89s | **11.00s** | 11.12s |

微基准层面 compress cl=6 12.4→12.3ms、PIL PNG 24.8→24.8ms 全指标零收益; 真实基准层面 SVE vs NEON 的 zlib 合计仅差 10ms/任务、E2E 差 0.12s（噪声内）。**零收益判定在两个层面一致。**

**原因分析**: 孤立 1.8x 的内循环在真实 deflate 中占比很小——本负载（图像数据, cl=6）的时间大头在哈希链遍历/插入/哈夫曼编码, 且 match 大多很快判定, compare256 不是真瓶颈。与"叶模块 Cython 无收益"同一教训: **孤立热点 ≠ 上下文热点, 必须集成实测**。

**结论**: SVE 在本硬件（SVE1 + cracked 256-bit）与本负载上无价值, 不采纳; 若未来上 Neoverse V2 类真 256-bit 通路硬件可重估。工程产物（验证过的 SVE 实现与集成方法）保留于 `~/pdfbuild/`。
