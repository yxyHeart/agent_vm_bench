# XLSX 通用栈优化实验：底层库 + CPU 层面的四组 AB

> 日期: 2026-08-31 ｜ 场景: 2核4G docker 容器, XLSX 文档基准
> 约束: **不改 workflow、不识别特定 Sheet/文件结构、不跳过任何步骤**——只优化同一套 openpyxl / Python / ZIP / LibreOffice 调用在底层的执行效率。任何新的 XLSX 流程进来应自动受益。
> 结论先行: 通用栈组合收益 **-9.3%(257.5s → 233.5s)**, 全部来自"本机自建 PGO+LTO+tsv110 CPython + lxml 写路径"; 换官方优化构建、zlib-ng、CPU 绑核三项证伪。此前四轮 -77.7% 的工作负载感知层已归档为实验数据, 与本路线互斥。

## 一、实验设计

阶梯分组, 每组之间只动一个变量, XLSX workflow 一行不改:

| 组 | 配置 | 变量 |
|----|------|------|
| A | 原版镜像(Ubuntu 24.04 发行版 python3.12, 无 PGO/LTO) | 基线 |
| B | 官方 `python:3.12.3-slim` 的 PGO+LTO CPython overlay | 换解释器二进制 |
| B2 | 本机自建 CPython 3.12.3: gcc `-O3 -mcpu=tsv110` + openpyxl 工作负载 PGO + computed gotos | 为鲲鹏定制(无 LTO) |
| B2L | B2 + `--with-lto` | 补 LTO |
| B2LX | B2L + lxml(openpyxl 自动切 lxml 写路径, 读路径不受影响) | 库级写加速 |
| C | A + zlib-ng 2.2.4 (zlib-compat, LD_PRELOAD) | 换压缩库(影响 python zipfile + LibreOffice 全体) |
| D | A 的 `--cpus=2` 配额 → `--cpuset-cpus=44,45 --cpuset-mems=1` | CPU 绑核 |

测量: 单次冷加载(22s 量级)与存盘(25s 量级)微基准各 2~3 次取稳态; 代表组跑完整 bench-core E2E(fixed 单任务)。

## 二、结果总表

| 组 | 冷加载 | 存盘 | E2E | 判定 |
|----|----:|----:|----:|------|
| A 基线 | 22.19~22.58s | 25.45~25.93s | **257.5s** | — |
| B 官方 PGO/LTO | 23.62~23.85s | 27.79~28.19s | 未跑 | **负收益, 证伪** |
| B2 自建 PGO(无 LTO) | 21.48s | 25.15s | 251.0s (-2.5%) | 小幅正收益 |
| B2L +LTO | 19.64~21.00s | 22.46~23.66s | **237.4s (-7.8%)** | LTO 是关键拼图 |
| B2LX +lxml 写路径 | 19.77~20.48s | 20.50~21.51s | **233.5s (-9.3%)** | 当前推荐组合 |
| C zlib-ng | 22.28s | 25.19s | 未跑 | **持平, 证伪** |
| D cpuset | 22.22~22.33s | 25.61~25.78s | 未跑 | **持平, 证伪** |

辅助证据: B 在纯解释器循环(3×10⁷ 次加法)上也慢 12%(2.73s vs 2.44s)——退化是解释器本身, 与 openpyxl 无关; C/D 的 LibreOffice 重算(65.34s vs 65.79s)与 Python 侧均持平; cgroup `nr_throttled=0`(无限流), `MAX_CONCURRENCY=1/2/4` AB 持平(工作簿仅 36 公式, Calc 多线程无从发力), governor 已是 performance。

## 三、逐项分析

### B(官方 PGO/LTO 构建)——负收益, 为什么

`python:3.12.3-slim-bookworm` 的 CPython 由 GCC 12.2 在通用 armv8-a 目标上构建(带 pyperformance 训练的 PGO + LTO)。在鲲鹏(CPU part 0xd02)上, 它比 Ubuntu 24.04 发行版构建(GCC 13, computed gotos)慢 6~12%, 纯解释器循环亦然。结论: **PGO/LTO 不是免费午餐, 训练画像与目标微架构不匹配时是负资产**; "换个官方优化构建"这条路在本机证伪。

### B2 / B2L(本机自建)——唯一显著正收益

构建配方(全部在 j 机本机完成, 无需 root):

```text
gcc 12.3 (openEuler 24.03)
-O3 -mcpu=tsv110          ← CPU part 0xd02, gcc 无 tsv120, 取最近邻
--with-computed-gotos
--with-lto                ← 单独贡献约 -5% E2E(跨模块内联对解释器大循环价值显著)
PGO 训练 = openpyxl 工作负载语料(非 pyperformance):
  小表: 建/读/改/存 + 公式 + 合并 + 图表 + 样式 + read_only 流式
  大表: 123MB 模板全量 load + 3000 行遍历 + save
训练真实性: 276 个 .gcda 覆盖文件, 语料产物 corr_big.xlsx(12.3MB)生成
```

收益归因(E2E 257.5 → 233.5s, 逐调用): 纯 openpyxl 加载调用 -14~18%(TP-09: 20.9→18.4s; TP-14: 20.5→18.1s; TP-04: 29.5→26.1s), 含存盘调用 -12%(TP-07: 51.3→45.1s), LibreOffice 主导调用 -7%(TP-08: 62.7→58.5s)。即: **解释器层优化作用于全部 Python 时间(本负载约占 75%), 自建组合让这段整体快了 ~12%**。

### B2LX(lxml 写路径)——库级透明加速

装上 lxml 后 openpyxl **写**路径自动切换(读路径在 3.1.5 源码里无条件走标准库, 之前已实测互不影响)。这是 openpyxl 原生特性, 不改任何调用。存盘再 -1.2~2.4s, E2E 净 -3.9s。

### C(zlib-ng)——持平, 符合 PMU 预测

zlib-ng 2.2.4(zlib-compat)预加载后 python/LibreOffice 全部正常(symbol 兼容无问题), 但加载/存盘均在噪声内。原因: 该工作簿 123MB XML 的 inflate+deflate 全程只占 ~1s 量级, 之前 PMU 里 libexpat 也仅 6.5%——**压缩层从来不是这个工作负载的瓶颈**。"ARM SIMD 应该用在 zlib"的猜想方向正确但前提(压缩占比高)不成立。

### D(CPU 绑核)——持平

`--cpus=2` 配额与 `--cpuset` 绑核(同 NUMA 节点两核)在 Python 侧与 LibreOffice 侧均无差异; cgroup 无限流记录, governor=performance 无 DVFS 噪声。2 vCPU 配额没有"骗"调度器。作为压尾延迟的手段仍可留档, 但对本工作负载无性能收益。

## 四、PMU 采集受限说明

openEuler 内核对非 root 用户禁用 perf attach("Access to performance monitoring and observability operations is limited"), 本轮 PMU 计数(cycles/instructions/IPC)无法采集; 归因全部基于壁钟(逐调用计时 + 单变量阶梯)。

## 五、结论与下一步

1. **通用栈的现实**: 自建 PGO+LTO+tsv110 解释器 + lxml 写路径, 合计 **-9.3%**, 对任意 XLSX(乃至任意 Python)工作负载自动生效, 零行为风险。官方优化构建/zlib-ng/cpuset 三项证伪。
2. 此前四轮 -77.7% 的收益来自"让 CPU 不执行那些指令"(缓存/懒物化), 那类手段必须感知工作负载结构, 与"零感知"约束互斥——这是数量级差异的根因, 不是实现水平的差异。
3. **符合约束且上限最高的方向是 openpyxl 通用 native 加速**(`_speedups` C/Rust 扩展): 把 `bind_cells`/`write_cell`/坐标转换等**所有 XLSX 工作流通用**的百万次热点循环下沉为 native loop。它不识别任何文件结构, 对任意 openpyxl 流程生效, 作用对象正是 190B 指令里的大头(对象构造/绑定/序列化协议税)。建议作为下一阶段主线——通用栈(-9.3%)与它叠加后, 才是"底层路线"的完整形态。

## 六、文件与复现

| 文件 | 作用 |
|------|------|
| `patches/py312k/build.sh` | 自建 CPython 配方(configure + profile-opt) |
| `patches/py312k/corpus.py` | openpyxl 工作负载 PGO 训练语料 |
| `patches/py312k/Dockerfile` | 自建 python 镜像层(pyroot + wheels 解包) |
| `config/common/document-xlsx-gen-b2l.yaml` | 推荐组合配置(gen-b2l 镜像) |

```bash
# 在 aarch64 Linux 宿主(gcc + make)上:
dnf download zlib-devel openssl-devel && mkdir rpmroot && cd rpmroot && for r in ../*.rpm; do rpm2cpio $r | cpio -idm; done
bash patches/py312k/build.sh            # 产出 build-gen/pyroot (~20min)
# wheels(openpyxl/et_xmlfile/pdf2image/pillow/pypdf + lxml)解包进 pyroot/lib/python3.12/site-packages
docker build -t ubuntu-document-bench:gen-b2l build-gen/imgctx/
bench-core --provider docker --config config/common/document-xlsx-gen-b2l.yaml -n 1
```

镜像: A = `ubuntu-document-bench:24.04-linuxarm64`; B = `gen-b`; B2 = `gen-b2`(LTO); B2L = `gen-b2l`(**当前推荐**)。

