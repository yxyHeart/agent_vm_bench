# PDF 基准优化前后火焰图对比分析 (系统 zlib vs zlib-ng)

> 日期: 2026-09-03
> 数据源: `docs/data/pdf-analysis/flamegraph/` (before/after.folded + 5 个 SVG, 采集方法见同目录 README)
> 口径: py-spy 99Hz native 采样, 同一 workload (复刻 P03: 10×fill[配方 18 字段] + 10×render[pdftoppm -r 200 + PIL cl=6] × 3 轮), 样本数 ∝ Python 进程 CPU 时间。单变量: 只替换 libz (LD_PRELOAD zlib-ng 2.2.4), 其余条件完全一致。
> 读图入口: `png-zlib-before/after.svg` (PNG 编码→zlib 路径主对比), `flame-diff.svg` (差分), `flame-full-before/after.svg` (全景)。

## 一、总览 (表 1)

| 指标 | 优化前 (系统 zlib) | 优化后 (zlib-ng) | 变化 |
|---|---:|---:|---:|
| 总样本 | 2,080 | 1,577 | **-24.2%** |
| render 路径样本 | 1,460 (70.2%) | 916 (58.1%) | -37.3% |
| fill 路径样本 (未优化对照) | 605 (29.1%) | 638 (40.5%) | +5.5% (持平, 噪声内) |
| zlib 帧样本 | **948 (45.6%)** | **477 (30.2%)** | **-49.7%** |

- 总样本 -24.2% = Python 进程 CPU 时间缩水近四分之一, 与 E2E 同窗 A/B (-8.6%, 含未采样的 pdftoppm 子进程与 I/O 等待) 方向一致。
- 采样误差: 每轮 76-80 errors (~4%), 两变体同等影响, 不影响对比结论。

## 二、叶帧热点对比 (表 2, 按函数名聚合、绝对样本数)

| 叶帧 | 优化前 | 优化后 | 判读 |
|---|---:|---:|---|
| zlib 压缩 (模块级) | 943 (45.3%) | 474 (30.1%) | **唯一大幅变化 (-50%)** |
| PIL native 胶水 (ZipEncode/Unpack/Pack) | 451 (21.7%) | 393 (24.9%) | 绝对量持平 (-12.9%, 噪声内) |
| pypdf 解析 (read_*/\_\_new\_\_*/BytesIO) | 236 (11.3%) | 259 (16.4%) | 持平 (+9.7%, 噪声内) |
| pypdf 拷贝簿记 (clone/_reference) | 147 (7.1%) | 133 (8.4%) | 持平 |
| pypdf 写出 (write/renumber) | 101 (4.9%) | 115 (7.3%) | 持平 |

未优化路径**占比上升是分母效应**: 总量缩水、自身没变, 绝对样本数全部在采样噪声内。
优化前 libz 帧为单一暗块 (`libz内部(符号剥离)`, 发行版剥离); 优化后自编译带符号, 内部函数名可见。

## 三、zlib-ng 内部构成 (表 3, 475 个含 zlib 帧样本, 嵌套口径)

| 函数 | 样本 | 占 zlib 样本比 | 说明 |
|---|---:|---:|---|
| `deflate_medium` | 475 | 100% (容器帧) | 主压缩循环 |
| `longest_match_neon` | 190 | ~40% | NEON 向量化最长匹配查找 |
| `insert_string` / `quick_insert_string` | 161 | ~34% | 哈希表管理 |
| `zng_tr_flush_block` / `compress_block` / `fill_window` / `slide_hash_neon` | ~96 | ~20% | 落盘与簿记 |
| `adler32_fold_copy_c` 等 | ~6 | ~1% | 校验和 |

## 四、分析结论

1. **单变量归因闭合**: 只换 libz → zlib 帧砍半 (-49.7%), fill 侧全部 pypdf 叶帧绝对量持平, 差分图无任何显著红帧 (最大 +0.95%, 噪声量级) —— 收益 100% 来自 zlib-ng 替换, 且无副作用。这是对 "-8.6% E2E 收益来自 zlib-ng" 这一因果链的采样级证据。
2. **独立交叉验证**: 火焰图口径 zlib -49.7% vs zcount 探针口径 deflate 内部 -57% (1,326→568ms), 两种无关测量 (采样 vs LD_PRELOAD 拦截计时) 方向与量级一致。
3. **机制对应**: zlib-ng 内 ~74% 时间在 NEON 匹配查找 + 哈希管理 (`longest_match_neon` + `insert_string*`), 正是相对系统 zlib 的现代化部分 —— 收益来源与机制解释吻合 (向量化整块比对 + 现代化哈希)。
4. **瓶颈已转移**: 优化后 PNG 路径内 zlib 52% vs PIL 编码调度胶水 47%, 已接近 1:1 —— 继续提速需改 Pillow 逐 tile 调度 (超出零侵入约束), libz 侧余量已小。这是 "为什么不继续深挖 zlib" 的依据。
5. **下一个通用优化对象**: pypdf 解析链 (`read_object` + `read_until_regex` + `read_from_stream`, 合计 ~16.4%/259 样本) 成为 fill 侧最大热点, 对应 roadmap Phase B/C (native serializer/parser) 的入口证据。
