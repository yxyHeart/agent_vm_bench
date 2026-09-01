# PDF 优化 patches

`generic/` 为现役主线; 其余已关闭/归档的路线全部在 `archive/`。

## `generic/` — 通用底层优化 (现役主线)

零 workflow 侵入: 系统级 zlib-ng 替换 (LD_PRELOAD) + pypdf 协议继承移除。
产物镜像: `ubuntu-document-bench:pdf-generic` (11.98 → 10.96s, -8.5%)。
详见 `README.md` 与 `docs/pdf-generic-optimization-roadmap.md`。

## `archive/` — 已关闭路线 (保留可追溯)

| 目录/文件 | 原路线 | 关闭原因 |
|-----------|--------|---------|
| `workflow-aware/` | 流程级注入优化 (.pth 单模块: 进程合并/缓存/流水线/cl=1) | 对特定流程有侵入, 不适用于新流程; 成果 11.96→5.42s 归档为极限参考, 详见 `docs/pdf-optimization-report.md` |
| `Dockerfile.zng-sve` + `compare256_neon.c.patched` (构建 zng-base/zng-sve 对照库, `Dockerfile.probe` 的 VARIANT 依赖它) | zlib-ng 热点函数 SVE 向量化 | 孤立微基准 1.8x 但真实 E2E 零收益 (硬件疑为 cracked 2×128 SVE); 待真 256-bit 硬件可重估 |
| `cython_build.py` | pypdf Cython 编译 (全包/叶模块) | 全包有语义 bug, 叶模块无收益; 技术路线改窄接口 C 扩展 (见 roadmap Phase B/C) |
| `collect-bench.sh` | 早期探针采集脚本 (轮询式) | 被 `generic/collect-exact-bench.sh` 取代 (容器复用 pid 冲突漏采) |
| `check_patch.py` | 协议补丁独立验证脚本 | 已并入 `generic3_setup.sh` 构建期断言 |

> 历史注记: `pdf_pil_fastpng.py/.pth` (优化1的最初独立形态) 已并入 `pdf_accel.py`, 文件删除。
