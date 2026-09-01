# PDF patches

PDF 文档基准的优化产物, 按状态分档: `active/`(在用, 每个子目录一个优化点)、`archive/`(废弃留档)。

**当前生产镜像 = `active/` 两项叠加** (`zlib-ng` + `pypdf-protocol-patch`):
E2E **11.98s → 10.96s (-8.5%)**, Success 100%。零 workflow 侵入, 可平移到任何 pypdf/Pillow/zlib 负载。

## active/

### zlib-ng/ — 系统压缩库替换 (E2E -0.89s)

源码编译 zlib-ng 2.2.4 (zlib-compat, `-O3 -mcpu=tsv110`, ARM NEON 向量化),
以 `LD_PRELOAD` 系统级替换, 上层零感知; 删一个 ENV 即回退。
zlib 内部耗时 -58% (1,465→620ms/任务)。
- `Dockerfile.toolchain` → `Dockerfile.build-libs` → `Dockerfile.runtime` 顺序构建
  (toolchain/build-libs 两层同时服务 probe 与 archive 实验)

### pypdf-protocol-patch/ — pypdf 运行时协议继承移除 (E2E -0.22s)

`PdfObject`/`XmpInformation` 去掉 typing Protocol 基类 (2 处 sed), 消除 6.2 万次/clone
的慢速协议 isinstance; 单次复制 -14.4%, 输出逐字节一致。具备回馈 upstream 条件。
- `runtime-setup.sh` 构建期执行 + 双断言; `check_patch.py` 独立验证脚本

### probe-zlib/ — zlib 调用计量工具

`libzcount.so` 探针 (LD_PRELOAD 拦截 deflate/inflate, 精确计数+计时;
日志按 pid+starttime 命名防容器 pid 复用覆盖) + 三变体计量镜像 + bench 收割脚本。
用于任意 workload 的 zlib 耗时归因。

## archive/

| 目录 | 优化点 | 关闭原因 |
|------|--------|---------|
| `workflow-aware-pipeline/` | 流程级注入 (进程合并/缓存/流水线/cl=1, 11.96→5.42s) | 对特定流程侵入, 不适用新流程; 归档为极限参考 |
| `sve-compare256/` | zlib-ng 热点函数 SVE 向量化 | 孤立 1.8x 但真实 E2E 零收益 (疑 cracked 2×128 SVE); 待真 256-bit 硬件重估 |
| `cython-pypdf/` | pypdf Cython 编译 | 全包语义 bug, 叶模块无收益; 路线改窄接口 C 扩展 |

> 历史注记: `pdf_pil_fastpng.py/.pth` 已并入 `workflow-aware-pipeline/pdf_accel.py`, 删除。
