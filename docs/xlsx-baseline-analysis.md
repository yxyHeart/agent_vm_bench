# XLSX 基准优化前耗时分析: openpyxl 读写盘点

> 对全部 recipe 命令与冻结脚本源码逐一盘点(含脚本内部, 按实际执行路径计):

```text
全量 load_workbook ×9:
  TP-04 模板(结构)   TP-05 副本(图表)   TP-07 增强输入
  TP-08 ×2 重算后查错误(data_only=True) + 数公式(False)
  TP-09 读公式       TP-10 读值         TP-13 校验(verify_formula_workbook, 可编辑 1 次)
  TP-14 汇总
read_only 流式 ×3:  TP-12 导 CSV ×1 + TP-13 校验内 ×2   (1.7s 级, 忽略)
Workbook.save   ×1:  TP-07 增强输出(全流程唯一写)
```

关键结构: **同一份 123.5MB / 12.3 万行 / 250 万格工作簿被完整解析 9 次**, 每次都是
独立 `python3` 进程(`docker exec`), 内存对象树用完即弃, 跨调用零复用。
9 × ~19s = 全流程的大头。

## openpyxl 占 E2E 耗时

E2E 总计 257.5s, 其中 openpyxl(全量加载 ×9 + TP-07 的 save, 含 TP-08 内部的 2 次加载):

| 项 | 耗时 | 占 E2E |
|----|----:|----:|
| 全量加载 ×9(单次 ~19-30s) | 192.7s | 74.8% |
| TP-07 内 save(250 万格逐格序列化) | ~25s | ~9.7% |
| **openpyxl 合计** | **~218s** | **~84.6%** |

其余: LibreOffice 重算(soffice 本体) ~16s(6.2%), 杂项 I/O ~2.2s(0.9%), 流式读 ~1.7s。
