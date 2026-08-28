# PDF 基准测试 PIL PNG 压缩优化报告

> 日期: 2026-08-28
> 优化点: PIL Image.save compress_level 6→1 (透明注入)
> 硬件: Kunpeng 920B, 2核4G 容器, AArch64

## 一、优化背景

PDF 基准测试 (OF-306 表单批量填充) 单任务 12.0s，其中 P03 阶段 (批量填充+渲染) 占 71% (8.5s)。P03 内部 10 次 PDF 填充 (3.3s) + 10 次 PDF 渲染转 PNG (4.9s)，渲染是最大子项。

每次渲染调用 `convert_pdf_to_images.py`，内部 `pdf2image.convert_from_path()` 生成 PPM 位图后用 PIL 保存 3 张 PNG。PIL 默认 `compress_level=6` 的 zlib 压缩占单次渲染 71% (0.46s/0.65s)。

## 二、优化方案

通过 `.pth` 文件在 Python 启动时注入 `pdf_pil_fastpng.py`，monkey-patch `PIL.Image.Image.save`：当保存格式为 PNG 且未显式指定 `compress_level` 时，自动设为 1。

- **注入方式**: `pdf_pil_fastpng.pth` 放入 `dist-packages/`，Python 启动时自动 import
- **零启动开销**: 用 `builtins.__import__` hook 懒加载，首次 import PIL 时才 patch，不提前导入 PIL
- **不改 recipe / 不改 skill 脚本**: 对上层完全透明
- **镜像层**: `Dockerfile.pdf-opt` 一层 COPY，基于基础镜像叠加

## 三、正确性保证

PNG 是无损压缩格式，`compress_level` 仅控制 zlib 压缩强度，不影响像素内容：

| | compress_level=6 (默认) | compress_level=1 |
|---|---|---|
| 像素内容 | 完全一致 | **完全一致 (bit-identical)** |
| 文件大小 | ~660KB/页 | ~700KB/页 (+5%) |
| 压缩耗时 | ~0.15s/页 | ~0.08s/页 |
| 解压/读取 | 不变 | 不变 |

P04 验证阶段使用 `ImageChops.difference` 做模板与填充结果的像素级对比（阈值 >500 像素差异），像素不变则验证结果不变。端到端 `business_verification.json` status=success，100% 通过。

## 四、端到端验证结果

容器内 2核4G, 9 轮 round-robin, 1 sandbox:

| 阶段 | Baseline | +PIL cl=1 | 节省 | 降幅 |
|------|------:|------:|------:|----:|
| P01-inspect_prepare | 1,680ms | 1,579ms | 101ms | -6.0% |
| P02-build | 515ms | 506ms | 9ms | -1.7% |
| **P03-process_publish** | **8,528ms** | **7,636ms** | **892ms** | **-10.5%** |
| P04-verify_deliver | 1,074ms | 1,019ms | 55ms | -5.1% |
| **总计** | **11,997ms** | **10,904ms** | **1,093ms** | **-9.1%** |
| p99 | 12,054ms | 10,961ms | 1,093ms | -9.1% |
| 成功率 | 14/14 (100%) | 9/9 (100%) | — | — |
| 尾延迟 | 1.04x | 1.01x | — | — |

### 阶段降幅分析

- **P03 降幅最大 (-892ms, -10.5%)**：10 次渲染 × 3 页 PNG = 30 张，每张省 ~30ms
- **P01 也受益 (-101ms, -6.0%)**：模板渲染 3 张 PNG，每张省 ~30ms
- **P04 小幅受益 (-55ms)**：验证阶段 10 次 `ImageChops.difference` 读取 PNG，解压速度不变但可能 I/O 略快
- **P02 无变化**：纯文件写入，不涉及 PNG

## 五、文件清单

| 文件 | 说明 |
|------|------|
| `patches/pdf_pil_fastpng.py` | monkey-patch 核心 (懒加载 __import__ hook) |
| `patches/pdf_pil_fastpng.pth` | `.pth` 注入文件 (内容 `import pdf_pil_fastpng`) |
| `patches/Dockerfile.pdf-opt` | 镜像 overlay (基础镜像 + COPY 一层) |
| `config/common/document-pdf.yaml` | 配置已切到 `image: ubuntu-document-bench:pdf-opt` |

## 六、结论

PIL PNG 压缩优化 (compress_level 6→1) 实现 12.0s → 10.9s (**-9.1%**)，零正确性风险，零 recipe 改动，通过 `.pth` 透明注入。这是 CPU 侧 zlib 压缩计算的直接节省，无副作用。
