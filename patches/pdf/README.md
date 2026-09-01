# PDF 优化 patches

两条轨道, 互不依赖:

## `generic/` — 通用底层优化 (现役主线)

零 workflow 侵入: 系统级 zlib-ng 替换 (LD_PRELOAD) + pypdf 协议继承移除。
详见 `README.md` 与 `docs/pdf-generic-optimization-roadmap.md`。
产物镜像: `ubuntu-document-bench:pdf-generic` (11.98 → 10.96s, -8.5%)。

## `workflow-aware/` — 流程级注入优化 (已归档)

透明注入层 (`.pth` 单模块): subprocess 拦截/进程合并、解析缓存、原生尺寸渲染、
双核流水线、PNG cl=1。对特定流程有侵入, 不适用于新流程, 保留作极限性能参考。
产物镜像: `ubuntu-document-bench:pdf-opt` (11.96 → 5.42s, -54.7%)。
详见 `docs/pdf-optimization-report.md`。

> 历史: `pdf_pil_fastpng.py/.pth` (优化1的最初独立形态) 已并入 `pdf_accel.py`, 删除。
