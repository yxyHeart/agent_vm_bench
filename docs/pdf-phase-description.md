# PDF 基准测试 4 阶段流程说明

> 对象: PDF OF-306 表单批量填充 (10 申请人 × 3 页 PDF)
> 输入: `of306_aug2023.pdf` (OPM OF-306 表格, 249KB, 3 页, 47 字段)
> 输出: 10 份填充 PDF + 33 张渲染 PNG + 业务验收报告

## 全量阶段-步骤-脚本说明

| 阶段 | 子步骤 | 函数 | 脚本/命令 | 做了什么 |
|------|--------|------|-----------|----------|
| **P01-inspect_prepare** | 1 | read | `skills/pdf/SKILL.md` | 读取 PDF Skill 使用指南 |
| | 2 | read | `skills/pdf/forms.md` | 读取表单操作规范 (字段类型/填写规则/隐私约束) |
| | 3 | read | `input/verify_pdf_batch.py` | 读取业务验收脚本 (了解验收标准) |
| | 4 | read | `scripts/check_fillable_fields.py` | 读取字段检查脚本源码 |
| | 5 | read | `scripts/extract_form_field_info.py` | 读取字段信息提取脚本源码 |
| | 6 | read | `scripts/fill_fillable_fields.py` | 读取表单填充脚本源码 |
| | 7 | read | `scripts/convert_pdf_to_images.py` | 读取 PDF 转图片脚本源码 |
| | 8 | exec | `mkdir -p output/{rendered/template,field_values,filled}` | 创建输出目录结构 |
| | 9 | exec | `check_fillable_fields.py of306.pdf` | 检查 PDF 是否包含可填写表单字段 (pypdf get_fields) |
| | 10 | exec | `cat check_fillable_fields.log` | 读取检查结果日志 |
| | 11 | exec | `extract_form_field_info.py of306.pdf form_field_info.json` | 提取 38 个字段信息 (field_id/type/page/radio_options), 输出 JSON |
| | 12 | read | `form_field_info.json` | 读取提取的字段信息 (确认字段 ID 和页码) |
| | 13 | exec | `convert_pdf_to_images.py of306.pdf rendered/template/` | 渲染空白模板为 3 张 PNG (200dpi, pdftoppm+PIL) |
| **P02-build** | 1 | write | `generate_and_run_batch.py` | 写入批量生成脚本 (读取 synthetic_applicants.json, 为 10 个申请人各生成 14 字段的 field-value JSON) |
| | 2 | exec | `python3 generate_and_run_batch.py` | 运行生成脚本, 输出 10 份 `applicant_XX.json` (排除 SSN/签名/日期等敏感字段) |
| | 3 | exec | `python3 -c "validate field IDs..."` | 内联验证: 检查所有 field_id 存在、页码匹配、敏感字段无交集 |
| | 4 | write | `run_batch_fill_render.py` | 写入批量填充+渲染脚本 (10 次 fill + 10 次 render 的 subprocess 循环) |
| **P03-process_publish** | 1 | exec | `python3 run_batch_fill_render.py` | 运行批量处理: 对 10 个申请人依次执行填充和渲染 |
| | | | ↳ 10× `fill_fillable_fields.py` | pypdf 读取模板 → PdfWriter(clone_from) → update_page_form_field_values → write 输出填充后 PDF |
| | | | ↳ 10× `convert_pdf_to_images.py` | pdf2image (pdftoppm 200dpi) 渲染填充后 PDF 为 3 张 PNG (共 30 页 + 模板 3 页 = 33 张) |
| | 2 | write | `batch_summary.json` | 写入批处理摘要 (申请人数=10, PDF数=10, PNG数=33, 敏感字段留空=true) |
| **P04-verify_deliver** | 1 | exec | `verify_pdf_batch.py` | 严格业务验收: |
| | | | ↳ 模板检查 | 确认模板 3 页 + 38 个终端字段 |
| | | | ↳ 字段检查输出 | 确认 form_field_info.json 含 38 个字段 |
| | | | ↳ 模板渲染 | 确认 3 张模板 PNG 存在且 >10KB |
| | | | ↳ 10× 逐份验证 | 每份: PDF 3 页 + 字段值正确 (姓名/出生地/公民/电话/单选/共No) + 敏感字段空白 + 渲染 3 页 + 像素差异 >500 |
| | | | ↳ 批处理摘要 | 确认 filled_pdf_count=10, rendered_page_count=33 |
| | 2 | exec | `find + wc -l + ls + python3 -c` | 统计交付物: PNG 数=33, PDF 数=10, JSON 数=10, business_verification.json status=success |

## 脚本依赖关系

```
of306_aug2023.pdf (输入模板)
  │
  ├── check_fillable_fields.py ──→ check_fillable_fields.log
  ├── extract_form_field_info.py ──→ form_field_info.json (38 字段)
  ├── convert_pdf_to_images.py ──→ rendered/template/page_{1,2,3}.png
  │
  ├── synthetic_applicants.json (10 申请人数据)
  │     │
  │     └── generate_and_run_batch.py ──→ field_values/applicant_{01..10}.json
  │                                         │
  └── fill_fillable_fields.py ←─────────────┘ (每份 JSON)
        │
        └──→ filled/applicant_{01..10}.pdf
              │
              └── convert_pdf_to_images.py ──→ rendered/applicant_{01..10}/page_{1,2,3}.png

verify_pdf_batch.py ←── (模板 + 10 份填充结果 + 10 份 JSON + 摘要)
  └──→ business_verification.json (status=success)
```

## 脚本清单

| 脚本 | 来源 | 依赖库 | 调用次数/任务 | 功能 |
|------|------|--------|------:|------|
| `check_fillable_fields.py` | skill | pypdf | 1 | 检查 PDF 是否有可填写字段 |
| `extract_form_field_info.py` | skill | pypdf | 1 | 提取字段 ID/类型/页码/选项 |
| `fill_fillable_fields.py` | skill | pypdf | 10 | 填充表单字段值, 输出 PDF |
| `convert_pdf_to_images.py` | skill | pdf2image, PIL | 11 | PDF 转 PNG (模板 1 + 填充 10) |
| `generate_and_run_batch.py` | recipe P02 write | json | 1 | 生成 10 份字段值 JSON |
| `run_batch_fill_render.py` | recipe P02 write | subprocess | 1 | 循环调 fill+render 各 10 次 |
| `verify_pdf_batch.py` | seed input | pypdf, PIL | 1 | 业务验收 (字段值+像素差异) |
