# PDF 单次调用链路分析

> 日期: 2026-08-28
> 对象: PDF OF-306 表单批量填充基准 (10 申请人 × 3 页 PDF)
> 容器: 2核4G, ubuntu-document-bench:24.04-linuxarm64
> 数据来源: `[CALLTIMINGS]` JSON 日志 (document.py `_execute_phase` 埋点)

## 一、4 阶段总览

| 阶段 | 平均耗时 | 占比 | 说明 |
|------|------:|----:|------|
| PDF-P01-inspect_prepare | 1,680ms | 14.0% | 读取 SKILL/forms/脚本, 检查字段, 提取字段信息, 渲染空白模板 |
| PDF-P02-build | 515ms | 4.3% | 写入+运行 generate_and_run_batch.py (生成 10 JSON), 验证字段, 写 run_batch_fill_render.py |
| **PDF-P03-process_publish** | **8,528ms** | **71.1%** | **运行 run_batch_fill_render.py (10 填充 + 10 渲染)** |
| PDF-P04-verify_deliver | 1,074ms | 9.0% | 运行 verify_pdf_batch.py 业务验收 + 统计交付物 |
| **总计** | **11,997ms** | 100% | 14 轮稳定, p99=12,054ms, 尾延迟 1.04x |

## 全量测试点汇总

> 4 阶段共 21 次工具调用 (7 read + 4 write + 10 exec),每行一个测试点。

| # | 阶段 | idx | 函数 | 命令/路径 | 耗时 | 占比 | 瓶颈归因 |
|---:|------|----:|------|-----------|----:|----:|----------|
| 1 | P01 | 0 | read | `skills/pdf/SKILL.md` | 53ms | 0.4% | exec 通信开销 |
| 2 | P01 | 1 | read | `skills/pdf/forms.md` | 53ms | 0.4% | exec 通信开销 |
| 3 | P01 | 2 | read | `input/verify_pdf_batch.py` | 53ms | 0.4% | exec 通信开销 |
| 4 | P01 | 3 | read | `scripts/check_fillable_fields.py` | 53ms | 0.4% | exec 通信开销 |
| 5 | P01 | 4 | read | `scripts/extract_form_field_info.py` | 53ms | 0.4% | exec 通信开销 |
| 6 | P01 | 5 | read | `scripts/fill_fillable_fields.py` | 53ms | 0.4% | exec 通信开销 |
| 7 | P01 | 6 | read | `scripts/convert_pdf_to_images.py` | 53ms | 0.4% | exec 通信开销 |
| 8 | P01 | 7 | exec | `mkdir -p output/rendered/template output/field_values output/filled` | 53ms | 0.4% | exec 通信开销 |
| 9 | P01 | 8 | exec | `check_fillable_fields.py of306.pdf > check.log` | 229ms | 1.9% | Python启动 + pypdf导入 |
| 10 | P01 | 9 | exec | `cat check_fillable_fields.log` | 90ms | 0.8% | exec 通信开销 |
| 11 | P01 | 10 | exec | `extract_form_field_info.py of306.pdf form_field_info.json` | 232ms | 1.9% | Python启动 + pypdf get_fields() + 遍历annotations |
| 12 | P01 | 11 | read | `form_field_info.json` (38字段) | 90ms | 0.8% | exec 通信开销 |
| 13 | P01 | 12 | exec | `convert_pdf_to_images.py of306.pdf rendered/template/` (3页PNG) | 543ms | 4.5% | pdftoppm渲染 + **PIL PNG压缩(cl=6)** |
| 14 | P02 | 0 | write | `generate_and_run_batch.py` (helper源码) | 165ms | 1.4% | base64解码写文件 |
| 15 | P02 | 1 | exec | `python3 generate_and_run_batch.py` (生成10 JSON) | 82ms | 0.7% | Python启动 + JSON生成 |
| 16 | P02 | 2 | exec | `python3 -c "validate field IDs..."` | 100ms | 0.8% | Python启动 + 内联验证 |
| 17 | P02 | 3 | write | `run_batch_fill_render.py` (helper源码) | 154ms | 1.3% | base64解码写文件 |
| 18 | **P03** | **0** | **exec** | **`python3 run_batch_fill_render.py` (10填充+10渲染)** | **8,354ms** | **69.6%** | **见下方拆解** |
| 19 | P03 | 1 | write | `batch_summary.json` (固定内容) | 160ms | 1.3% | base64解码写文件 |
| 20 | P04 | 0 | exec | `verify_pdf_batch.py` (业务验收: 10 PDF字段+像素差异) | 944ms | 7.9% | 10× pypdf get_fields() + 10× PIL ImageChops |
| 21 | P04 | 1 | exec | `find + wc -l + ls + python3 -c` (交付物统计) | 115ms | 1.0% | exec 通信开销 |
| | | | | **合计** | **11,997ms** | **100%** | |

### 测试点 #18 (P03-exec) 内部拆解

`run_batch_fill_render.py` 内部 20 次 `subprocess.run`,每次 fill + render 交替:

| 子步 | 申请人 | fill (s) | render (s) | 累计 (s) |
|------|--------|------:|------:|------:|
| 1 | applicant_01 | 0.331 | 0.492 | 0.823 |
| 2 | applicant_02 | 0.332 | 0.488 | 1.643 |
| 3 | applicant_03 | 0.330 | 0.488 | 2.461 |
| 4 | applicant_04 | 0.332 | 0.489 | 3.282 |
| 5 | applicant_05 | 0.331 | 0.492 | 4.105 |
| 6 | applicant_06 | 0.331 | 0.485 | 4.921 |
| 7 | applicant_07 | 0.331 | 0.489 | 5.741 |
| 8 | applicant_08 | 0.333 | 0.487 | 6.561 |
| 9 | applicant_09 | 0.333 | 0.491 | 7.385 |
| 10 | applicant_10 | 0.333 | 0.489 | 8.207 |
| | **合计** | **3.317** | **4.891** | **8.208** |

### fill 单次内部 (0.33s)

| 子步骤 | 耗时 | 说明 |
|--------|----:|------|
| Python 启动 | 0.009s | 解释器初始化 |
| `import pypdf` | 0.099s | pypdf 模块加载 |
| `PdfReader(pdf)` | 0.003s | 打开 249KB PDF |
| `get_field_info(reader)` | 0.069s | 遍历 47 字段 + annotations 定位页码 |
| `PdfWriter(clone_from=reader)` | 0.110s | **深拷贝 PDF 结构树** |
| `update_page_form_field_values` | 0.002s | 写入 14 个字段值 |
| `set_need_appearances` | 0.000s | |
| `writer.write(f)` | 0.034s | 序列化输出 PDF |
| **合计** | **0.218s** | (+0.11s 启动导入 = 0.33s) |

### render 单次内部 (0.49s)

| 子步骤 | 耗时 | 说明 |
|--------|----:|------|
| Python 启动 | 0.009s | 解释器初始化 |
| `import pdf2image` | 0.050s | pdf2image 模块加载 |
| `import PIL.Image` | 0.039s | PIL 模块加载 |
| `convert_from_path(pdf, dpi=200)` | 0.190s | `pdftoppm -ppm` subprocess + PIL 加载 PPM |
| `image.save(×3, compress_level=6)` | 0.461s | **zlib 压缩 3 页 PNG** |
| **合计** | **0.651s** | (-0.16s 重叠 = 0.49s 子进程实测) |

## 二、P01-inspect_prepare (1,680ms) — 13 次工具调用

| idx | 函数 | 内容 | 耗时 |
|----:|------|------|----:|
| 0 | read | `/root/.openclaw/skills/pdf/SKILL.md` | 53ms |
| 1 | read | `/root/.openclaw/skills/pdf/forms.md` | 53ms |
| 2 | read | `.../SUB-MEM-PDF-01/input/verify_pdf_batch.py` | 53ms |
| 3 | read | `.../skills/pdf/scripts/check_fillable_fields.py` | 53ms |
| 4 | read | `.../skills/pdf/scripts/extract_form_field_info.py` | 53ms |
| 5 | read | `.../skills/pdf/scripts/fill_fillable_fields.py` | 53ms |
| 6 | read | `.../skills/pdf/scripts/convert_pdf_to_images.py` | 53ms |
| 7 | exec | `mkdir -p output/rendered/template output/field_values output/filled` | 53ms |
| 8 | exec | `check_fillable_fields.py of306.pdf > check_fillable_fields.log` | 229ms |
| 9 | exec | `cat check_fillable_fields.log` | 90ms |
| 10 | exec | `extract_form_field_info.py of306.pdf form_field_info.json` | 232ms |
| 11 | read | `form_field_info.json` (38 字段) | 90ms |
| 12 | exec | `convert_pdf_to_images.py of306.pdf rendered/template/` (3 页 PNG) | 543ms |

**小结**: 7 次 read 各 ~53ms (exec 开销, head -c 65536 探测); 3 个 Python 脚本 exec 各 ~230ms (Python 启动+pypdf 导入+执行); 模板渲染 543ms (pdf2image/pdftoppm 3 页 200dpi)。

## 三、P02-build (515ms) — 4 次工具调用

| idx | 函数 | 内容 | 耗时 |
|----:|------|------|----:|
| 0 | write | `generate_and_run_batch.py` (完整 helper 源码, base64 heredoc) | 165ms |
| 1 | exec | `python3 generate_and_run_batch.py` (生成 10 份 field-value JSON) | 82ms |
| 2 | exec | `python3 -c "validate field IDs..."` (内联验证脚本) | 100ms |
| 3 | write | `run_batch_fill_render.py` (完整 helper 源码, base64 heredoc) | 154ms |

**小结**: 纯 Python 逻辑 + 文件写入, 无重度计算。2 次 write 各 ~160ms (base64 解码写文件); 2 次 exec 各 ~90ms (Python 启动+执行)。

## 四、P03-process_publish (8,528ms) — 2 次工具调用

| idx | 函数 | 内容 | 耗时 |
|----:|------|------|----:|
| 0 | exec | `python3 run_batch_fill_render.py` (10 填充 + 10 渲染) | 8,354ms |
| 1 | write | `batch_summary.json` (固定内容) | 160ms |

### P03 idx=0 内部拆解 (容器内独立计时)

`run_batch_fill_render.py` 调用 10 次 fill + 10 次 render, 每次 `subprocess.run`:

```
每次 fill:  ~0.33s = Python启动(0.01s) + pypdf导入(0.10s) + PdfReader(0.003s) + get_field_info(0.069s) + PdfWriter(clone_from)(0.110s) + update_fields(0.002s) + writer.write(0.034s)
每次 render: ~0.49s = Python启动(0.01s) + pdf2image导入(0.05s) + PIL导入(0.04s) + convert_from_path(0.19s) + PIL save 3×PNG(0.46s) [其中 pdftoppm subprocess ~0.19s, PIL编码压缩 ~0.27s]
```

| 子步骤 | 单次 | ×10 | 占 P03 |
|--------|----:|----:|----:|
| fill (pypdf 填充) | 0.33s | 3.3s | 40% |
| render (pdf2image 渲染) | 0.49s | 4.9s | 60% |
| **合计** | **0.82s** | **8.2s** | 97% |

**render 内部细分**:

| 子步骤 | 单次 | 说明 |
|--------|----:|------|
| convert_from_path (pdftoppm subprocess + PPM 加载) | 0.19s | poppler 渲染 3 页 200dpi |
| PIL save 3× PNG (compress_level=6 默认) | 0.46s | zlib 压缩编码 |
| pdftoppm 直接调用 (-png) | 2.97s | poppler 自带 PNG 编码 (比 pdf2image+PIL 慢 6x!) |

> 关键发现: `pdf2image` 默认用 `pdftoppm -ppm` (输出原始 PPM, ~0.19s) + PIL 加载 + PIL save PNG (compress_level=6, ~0.46s)。直接 `pdftoppm -png` 反而需 3.0s (poppler 内部 PNG 编码慢)。

## 五、P04-verify_deliver (1,074ms) — 2 次工具调用

| idx | 函数 | 内容 | 耗时 |
|----:|------|------|----:|
| 0 | exec | `verify_pdf_batch.py` (业务验收: 10 PDF × 字段值检查 + 像素差异) | 944ms |
| 1 | exec | `find output + wc -l + ls + python3 -c` (交付物统计) | 115ms |

**verify_pdf_batch.py 内部**: 10 次 PdfReader.get_fields() + 10 次 PIL ImageChops.difference() (模板 vs 填充后 page_2 像素差异, 阈值 >500 像素)。Python 启动+pypdf 导入 ~0.1s, 10 PDF 验证 ~0.8s。

## 六、调用链路图

```
execute()  [12.0s]
├── prepare_workspace()  [cp -a /opt/document-bench/pdf → workspace]
├── P01-inspect_prepare  [1.68s]
│   ├── 7× read (SKILL.md, forms.md, verify_pdf_batch.py, 4 scripts)  [7×53ms = 0.37s]
│   ├── exec mkdir -p output/...  [53ms]
│   ├── exec check_fillable_fields.py  [229ms]  ← pypdf PdfReader.get_fields()
│   ├── exec cat log  [90ms]
│   ├── exec extract_form_field_info.py  [232ms]  ← pypdf get_fields() + 遍历 annotations
│   ├── read form_field_info.json  [90ms]
│   └── exec convert_pdf_to_images.py (模板 3 页)  [543ms]  ← pdftoppm + PIL save
├── P02-build  [0.52s]
│   ├── write generate_and_run_batch.py  [165ms]
│   ├── exec python3 generate_and_run_batch.py  [82ms]  ← 生成 10 JSON
│   ├── exec python3 -c "validate"  [100ms]
│   └── write run_batch_fill_render.py  [154ms]
├── P03-process_publish  [8.53s]  ← 绝对热点
│   ├── exec python3 run_batch_fill_render.py  [8.35s]
│   │   ├── 10× fill_fillable_fields.py subprocess  [10×0.33s = 3.3s]
│   │   │   └── pypdf: PdfReader(0.003s) + get_field_info(0.069s) + PdfWriter(clone_from)(0.110s) + update+write(0.036s) + Python启动+导入(0.11s)
│   │   └── 10× convert_pdf_to_images.py subprocess  [10×0.49s = 4.9s]
│   │       └── pdf2image: convert_from_path(0.19s, pdftoppm subprocess) + PIL save 3×PNG(0.46s, compress_level=6) + Python启动+导入(0.10s)
│   └── write batch_summary.json  [160ms]
├── P04-verify_deliver  [1.07s]
│   ├── exec verify_pdf_batch.py  [944ms]  ← 10× PdfReader.get_fields() + 10× PIL ImageChops.difference()
│   └── exec find + wc + ls + python3  [115ms]
└── validate_business_result()  ← python3 -c json check
```

## 七、瓶颈归因

### 瓶颈 #1: PIL PNG 压缩 (compress_level=6) — 4.6s/任务 (38%)

- `convert_pdf_to_images.py` 调用 `image.save(path)` 默认 compress_level=6
- 10 次渲染 × 3 页 = 30 个 PNG, 每个 ~0.15s zlib 压缩
- compress_level=6 → 1 时: 0.46s → 0.23s/渲染, 省 ~2.3s/任务
- 输出像素 bit-identical, 文件大小 +5%

### 瓶颈 #2: Python 子进程启动 + 库导入 — 2.1s/任务 (18%)

- 10× fill subprocess: Python 启动 0.01s + pypdf 导入 0.10s = 0.11s × 10 = 1.1s
- 10× render subprocess: Python 启动 0.01s + pdf2image+PIL 导入 0.09s = 0.10s × 10 = 1.0s
- 这 2.1s 纯粹是子进程启动开销, 无有效计算

### 瓶颈 #3: pypdf PdfWriter(clone_from) — 1.1s/任务 (9%)

- 每次 fill 都 `PdfWriter(clone_from=reader)`, 深拷贝整个 PDF 结构
- 10 × 0.11s = 1.1s
- 可通过缓存 PdfWriter 或复用 reader 减少

### 瓶颈 #4: pdftoppm 渲染 — 1.9s/任务 (16%)

- `convert_from_path` 内部调 `pdftoppm -ppm -r 200` 生成 PPM, PIL 加载
- 10 × 0.19s = 1.9s, 这是 poppler 的光栅化开销, 不可压缩

### 非瓶颈

- 7× read 探测 (P01): 0.37s — exec 通信开销, 固定
- P02 全部: 0.52s — 纯 Python 文件操作
- P04 verify: 1.07s — 必须的业务验证
- write batch_summary.json: 0.16s — 固定

## 八、优化矩阵

| 优化点 | 目标 | 预期节省 | 难度 | 状态 |
|--------|------|------:|------|------|
| PIL compress_level=1 | 瓶颈 #1 | ~2.3s (19%) | 低 (`.pth` 注入) | ✅ 已实现验证 |
| 子进程合并 (单 Python 跑 10×fill+render) | 瓶颈 #2 | ~2.1s (18%) | 高 (改 recipe helper) | 需改 run_batch_fill_render.py |
| PdfWriter 复用/缓存 | 瓶颈 #3 | ~1.0s (8%) | 中 (需改 fill 脚本) | 需改 fill_fillable_fields.py |
| pdftoppm 降 dpi (200→150) | 瓶颈 #4 | ~0.7s (6%) | 低 | 影响验证 (像素差异阈值) |

> 注: recipe JSON 和 skill 脚本不可修改, #2/#3 需透明注入层 (类似 XLSX 的 `.pth` 方案)。
