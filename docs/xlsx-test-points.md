# XLSX 测试点说明

测试点 = 上面工具调用链路里的 15 次调用,每次调用即一个测试点。外层框架不计。

| 测试点 | 阶段 | 函数 | 操作 | 类型 |
|--------|------|------|------|------|
| TP-01 | P01 inspect_prepare | read | 读 xlsx SKILL.md(确认可读) | I/O |
| TP-02 | P01 inspect_prepare | exec | `cat` 校验脚本源码 | I/O |
| TP-03 | P01 inspect_prepare | exec | `cp` 模板→工作副本 | I/O |
| TP-04 | P01 inspect_prepare | exec | `python3` openpyxl 全量加载(2.96M 行)查结构 | CPU |
| TP-05 | P01 inspect_prepare | exec | `python3` heredoc 注入图表(load+save) | CPU |
| TP-06 | P02 build | write | base64 heredoc 写 `enhance_workbook.py`(10KB) | I/O |
| TP-07 | P02 build | exec | `run_xlsx_helper_atomic.py` 原子增强(load+改+save+replace) | CPU |
| TP-08 | P03 process_publish | exec | `recalc.py` → LibreOffice 对 2.96M 行重算(fork soffice) | CPU(瓶颈) |
| TP-09 | P03 process_publish | exec | openpyxl `load_workbook(data_only=False)` 读公式 | CPU |
| TP-10 | P03 process_publish | exec | openpyxl `load_workbook(data_only=True)` 读计算值 | CPU |
| TP-11 | P03 process_publish | exec | `cat` 重算结果 JSON | I/O |
| TP-12 | P03 process_publish | exec | `export_xlsx_csv.py` 导出 Executive + Reconciliation 两 CSV | CPU+I/O |
| TP-13 | P04 verify_deliver | exec | `verify_xlsx_enhanced.py` 业务校验出 verification.json | CPU |
| TP-14 | P04 verify_deliver | exec | `write_xlsx_summary.py` 汇总特征/sha256→JSON | CPU |
| TP-15 | P04 verify_deliver | exec | `test -s` 断言交付物非空 | I/O |

> 每个测试点都经同一条原语链 `provider.exec → docker exec <c> sh -c '<cmd>'`,故另含一层 per-call 固定开销(daemon RPC + fork + `sh -c` + python 冷启动),对所有 15 点均适用。
