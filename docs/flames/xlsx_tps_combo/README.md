# XLSX 测试点火焰图（py-spy, 50Hz, 组合优化镜像容器内采集）

跳过零头/不涉及优化的测试点: TP-01/02/03(读文档/cat/cp)、TP-06(写脚本)、TP-11(cat JSON)、TP-15(test 断言)。
TP-07 因原子助手内部 subprocess 起子进程, 采用 attach 轮询方式采集; 其余均 py-spy 直接启动全程覆盖。

| 目录 | 形态 |
|------|------|
| `xlsx_tps_stock/` | 两层全关(OPENPYXL_CACHE=0 OPENPYXL_SPEEDUPS=0), 即原生行为 |
| `xlsx_tps_combo/` | 磁盘缓存 + speedups 两层全开(推荐组合) |

| 测试点 | stock 里看什么 | combo 里看什么 |
|--------|----------------|----------------|
| TP04_structure | parse_cell/Cell.__init__/bind_cells 密集(冷解析 ~22s) | 融合 C 循环帧(cython)+ 落盘 |
| TP05_charts | 同上冷解析 | cached_load_workbook 命中 + _rebuild_cells(~4s) |
| TP07_enhance | load 解析 + etree 序列化 save | load 命中 + save 原生(两层不碰) |
| TP08_recalc | recalc 两次全量解析(soffice 段为空转进程) | 两次加速解析 + 落盘 |
| TP09/10_formulas/values | 冷解析 | 命中重建 |
| TP12_csv | read_only 流式(两层均不适用) | 同左, 形态应与 stock 相近 |
| TP13_verify | 校验脚本 1 次全量解析 + 2 次流式 | 全量那次命中重建; 流式不变 |
| TP14_summary | 冷解析 | 命中重建 |
