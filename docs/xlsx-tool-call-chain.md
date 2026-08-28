# XLSX 工具调用链路报告

## 外层说明

外层(`run_benchmark` / `RoundRobinTaskManager` / `DocumentRoundRunner` / `StatsCollector` / 配方加载等)只是 **bench-core 的框架外壳**——一个模拟 agent 按固定剧本回放工具调用、外加评测仪表,用于造可复现负载。**无需关心它的时间**,真 agent 接进来这层会整体替换。本报告只聚焦里面真实 agent 会走的 **15 次工具调用**。

> 前置(外壳做的,不计入 15):`prepare_workspace` 把种子 `cp -a /opt/document-bench/xlsx → <WS>` 并建 `output/`,使每次任务起点一致。
> `<WS>` = `/root/.openclaw/workspace/tool-modeling/SUB-MEM-OFFICE-01`(容器内工作区)。

## 15 次工具调用

### P01 inspect_prepare — 检查与准备

| # | 函数 | 执行命令 | 做什么 |
|---|------|---------|--------|
| 1 | read | `test -f <WS>/SKILL.md && head -c 65536 <WS>/SKILL.md >/dev/null` | 确认 xlsx skill 文档在、可读 |
| 2 | exec | `cat <WS>/input/verify_xlsx_enhanced.py` | 读校验脚本源码 |
| 3 | exec | `cp <WS>/input/monthly_operations_template.xlsx <WS>/output/monthly_operations_report.xlsx` | 拷贝模板成工作副本(后续都改它) |
| 4 | exec | `cd <WS> && python3 -c "from openpyxl import load_workbook; wb=load_workbook('input/...template.xlsx', data_only=False); print('Sheets: ...')"` | openpyxl 全量加载(2.96M 行),查 sheet 结构 |
| 5 | exec | `cd <WS> && python3 <<'PYEOF' …openpyxl 注入 BarChart/LineChart/PieChart…` | 给 report 加图表,存盘 |

### P02 build — 增强

| # | 函数 | 执行命令 | 做什么 |
|---|------|---------|--------|
| 6 | write | `mkdir -p <WS>` + base64 heredoc 写 `enhance_workbook.py`(10KB) | 把增强 helper 脚本写到工作区 |
| 7 | exec | `cd <WS> && python3 /opt/document-bench/bin/run_xlsx_helper_atomic.py enhance_workbook.py output/monthly_operations_report.xlsx` | 原子化跑 helper:拷→改临时件→校验→`os.replace` 换回,防半成品 |

### P03 process_publish — 重算与导出(最重)

| # | 函数 | 执行命令 | 做什么 |
|---|------|---------|--------|
| 8 | exec | `cd <WS> && python3 /root/.openclaw/skills/xlsx/scripts/recalc.py output/monthly_operations_report.xlsx 180 > output/formula_recalc.json` | **LibreOffice headless 对 2.96M 行做公式重算**(recalc.py 内部再 fork `soffice`),结果写 JSON。瓶颈 |
| 9 | exec | `cd <WS> && python3 -c "openpyxl.load_workbook('...report.xlsx', data_only=False)…"` | 重算后再 load,读公式/结构 |
| 10 | exec | `cd <WS> && python3 -c "openpyxl.load_workbook('...report.xlsx', data_only=True)…"` | 再 load,读缓存计算值 |
| 11 | exec | `cat <WS>/output/formula_recalc.json` | 读重算结果 JSON |
| 12 | exec | `cd <WS> && python3 /opt/document-bench/bin/export_xlsx_csv.py output/monthly_operations_report.xlsx output/monthly_operations_summary.csv output/reconciliation_summary.csv` | openpyxl load(data_only)后导出 Executive_Summary + Reconciliation 两个 CSV,原子写 |

### P04 verify_deliver — 校验与交付

| # | 函数 | 执行命令 | 做什么 |
|---|------|---------|--------|
| 13 | exec | `cd <WS> && python3 input/verify_xlsx_enhanced.py output/monthly_operations_report.xlsx output/formula_recalc.json output/business_verification.json` | 跑业务校验,出 `business_verification.json`(`status=success` 才算过) |
| 14 | exec | `cd <WS> && python3 /opt/document-bench/bin/write_xlsx_summary.py output/monthly_operations_report.xlsx output/business_verification.json output/formula_recalc.json output/execution_summary.json output/monthly_operations_summary.csv output/reconciliation_summary.csv` | 汇总执行摘要:工作簿特征(公式/图表/下拉/sha256/行数)→ JSON |
| 15 | exec | `cd <WS> && test -s output/monthly_operations_report.xlsx && test -s output/monthly_operations_summary.csv && test -s output/reconciliation_summary.csv` | 断言所有交付物非空 |

## 全景

15 次调用 = **4 阶段串行**:`准备(P01)→ 增强(P02)→ 重算导出(P03)→ 校验交付(P04)`。每个调用都走同一条原语链 `provider.exec → docker exec <c> sh -c '<cmd>' → 容器内 fork 进程`。

主要开销集中在:① #8 的 LibreOffice 重算(CPU);② 多次 `openpyxl.load_workbook(2.96M 行)`(#4 #5 #7 #9 #10 #12 #13 #14);③ 15 次 `docker exec` 的 per-call 固定税(daemon RPC + fork + `sh -c` + python 冷启动)。
