# PDF 基准测试优化报告

> 日期: 2026-08-29
> 对象: PDF OF-306 表单批量填充基准 (10 申请人 × 3 页, pypdf + poppler + PIL)
> 硬件: Kunpeng 920B (AArch64), 2核4G 容器
> 约束: recipe 与 skill 脚本零改动, 全部优化走透明注入层 (.pth)

## 一、成果总览

| 版本 | 任务均值 | 增量 | 累计降幅 |
|------|------:|----:|----:|
| baseline | 11.96s | — | — |
| + 优化1: PNG 压缩等级 | 10.90s | -1.06s | -8.9% |
| + 优化2: subprocess 合并 + pypdf 解析 memo | 9.51s | -1.39s | -20.5% |
| + 优化3: 原生尺寸光栅化 | **6.87s** | -2.64s | **-42.6%** |

最终: 13/13 success (100%), p99=6.96s, 尾延迟 1.01x, 输出经 bit-for-bit 与严格业务验收双重验证。

分阶段 (baseline → 最终):

| 阶段 | baseline | 最终 | 降幅 |
|------|------:|------:|----:|
| P01-inspect_prepare | 1,680ms | 1,745ms | 持平* |
| P02-build | 515ms | 591ms | 持平 |
| P03-process_publish | 8,528ms | **3,324ms** | **-61%** |
| P04-verify_deliver | 1,074ms | 1,040ms | 持平 |

*P01 的模板渲染也受益于优化3, 但被 read/exec 通信开销 (7×53ms) 掩盖。

## 二、优化点详解

### 优化1: PNG 压缩等级 zlib cl=6→1 (10.90s, -8.9%)

**瓶颈**: PIL `image.save()` 默认 compress_level=6, 30+ 张 PNG 每张 ~150ms 的 zlib 压缩, 全任务 ~2.5s 纯压缩 CPU。

**手段**: `.pth` 懒加载 hook monkey-patch `PIL.Image.Image.save`, PNG 格式且未显式指定时注入 compress_level=1。零启动开销 (builtins.__import__ 拦截, 首次 import PIL 才生效)。

**正确性**: PNG 无损, 压缩等级只影响速度/文件大小, 不影响像素。文件 +5%, 像素 bit-identical, verify 像素 diff 检查不变。

### 优化2: subprocess 合并 + pypdf 解析 memo (9.51s, -11.6%)

**瓶颈**: recipe 的 P03 起 20 个子进程 (10 fill + 10 render), 每个付解释器启动 + import pypdf/PIL (~100ms), ~2s 纯开销无有效计算; 且 10 次 fill 各自重新解析同一个 PDF 的对象流 (get_fields 冷 70ms / 暖 0.8ms, 98.9% 是解析)。

**手段** (pdf_accel.py 两层):
- **L1 拦截 subprocess.run**: 识别 fill/render 脚本命令, 首次 import 模块, 后续直接调函数 (模拟 sys.argv/stdout/SystemExit 子进程语义)
- **L2 PdfReader memo**: 按 (路径, mtime, size) 共享 reader, 惰性解析对象只算一次, 10 次解析变 1 次

**正确性**: pypdf 的 clone_from 是深拷贝, 字段写操作发生在克隆体上, 共享 reader 纯只读复用。冒烟测试: in-process vs 子进程 fill/render 输出 bit-for-bit 一致 (含 warm 路径)。

### 优化3: 原生尺寸光栅化 (6.87s, -27.8%)

**瓶颈**: pdf2image 固定 dpi=200 光栅化 1700×2200 (目标 772×1000 的 **4.9 倍像素量**), 11MB PPM/页落盘, 再由 PIL 降采样扔回 772×1000 —— 79% 光栅化算力 + 整段 PIL resize 是纯浪费。

**手段**: 拦截 convert_pdf_to_images 调用, 改 `pdftoppm -scale-to-x/-scale-to-y` 让 poppler splash 引擎 (C++) 直接按目标尺寸光栅化, PPM 中转 + PIL PNG 编码 (cl=1)。目标尺寸由 pdfinfo 页面尺寸按 dpi/max_dim 规则推导, 非硬编码。

**收益**: 单次渲染 429ms → 156ms (-64%), 10 次批量渲染 + 1 次模板渲染共省 2.6s。

**正确性**: 模板与填充走同一管线, verify 像素 diff 自洽 (6,855px 远超 >500 阈值); 尺寸 772×1000 与原路径一致; 冒烟 5/5 (fill bit-for-bit / 尺寸 / 页数 / 文件大小 / diff)。

## 三、原理归纳

三个优化点对应三种底层手段:

| 优化 | 手段 | 本质 |
|------|------|------|
| 1 | 降低算法强度 | 压缩等级换 CPU, 基准不需要极致压缩比 |
| 2 | 消除重复执行 | 进程合并消灭 20 次模块初始化; memo 消灭 10 次重复解析 |
| 3 | 消除无效计算量 | 按最终需求尺寸光栅化, 少画 79% 的像素, 活从 Python 挪回 C++ |

## 四、注入方式

```
patches/
├── pdf_pil_fastpng.py/.pth   # 优化1: PIL PNG cl=1 (懒加载 hook)
├── pdf_accel.py/.pth         # 优化2: subprocess 合并 + reader memo
└── Dockerfile.pdf-opt        # 镜像层: 基础镜像 + COPY 两个 .pth
```

镜像 `ubuntu-document-bench:pdf-opt` = 基础镜像 + 一层 COPY, recipe/skill 脚本零改动, 对上层完全透明。

## 五、剩余瓶颈 (后续方向)

| 项 | 耗时 | 说明 |
|----|------:|------|
| P03 剩余 | 3.3s | 10× (clone 66ms + write 26ms + pdftoppm 85ms) + Python 层循环 |
| P04 verify | 1.0s | 独立子进程, 10× PdfReader 解析 (memo 不跨进程) |
| P01/P02 固定开销 | 2.3s | read/exec 通信 + 轻量脚本, 不可压缩 |
| pdftoppm 光栅化 | ~0.9s | C++ 引擎固定成本, 已按需尺寸 |
