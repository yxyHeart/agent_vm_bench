# XLSX 测试点火焰图（py-spy 0.4.2, 50Hz, 容器内采集）

跳过零头/不涉及优化的测试点: TP-01/02/03(读文档/cat/cp)、TP-06(写脚本)、TP-11(cat JSON)、TP-15(test 断言)。
两张目录 = 同一组合镜像容器, 仅环境变量不同(stock: OPENPYXL_CACHE=0 OPENPYXL_SPEEDUPS=0)。
TP-07 因原子助手 subprocess 起子进程采用 pgrep 轮询 attach; 其余 py-spy 直接启动全程覆盖。

## 总样本数对比(50Hz → 约 = 秒)

| 测试点 | stock | combo | 说明 |
|--------|------:|------:|------|
| TP04 结构检查(MISS) | 852 (~17s) | 801 (~16s) | 首次解析, combo 走 C 融合循环 |
| TP05 图表检查(HIT) | 864 (~17s) | 220 (~4.4s) | 命中重建 |
| TP07 增强(load HIT+save) | 729* (~14.6s*) | 810 (~16.2s) | *stock 为 attach, 偏晚错过部分 load 段 |
| TP08 重算+双读 | 650 (~13s) | 774 (~15.5s) | 仅 python 段; soffice 为子进程不在图内 |
| TP09 读公式(HIT) | 748 (~15s) | 211 (~4.2s) | 命中重建 |
| TP10 读值(HIT) | 749 (~15s) | 220 (~4.4s) | 命中重建 |
| TP12 导 CSV | 51 (~1s) | 52 (~1s) | 两组同构 = 流式两层均不适用 |
| TP13 业务校验 | 925 (~18.5s) | 335 (~6.7s) | 脚本内 1 次全量 load 命中 |
| TP14 汇总特征 | 732 (~14.6s) | 204 (~4.1s) | 命中重建 |

## 读图须知(采集方式的固有偏差)

1. **stock 组图里可见 `cached_load_workbook` wrapper 帧**: stock 用"组合镜像+环境变量关闭",
   .pth 注入的包装函数仍在调用栈上, 但内部透传原生 `_original_load` — 行为等价
   (原生解析 ~17s 采样与 stock 耗时吻合), 帧不纯净属预期。
2. **speedups 的收益体现为样本总数下降**: C 融合循环是 Cython 原生帧, py-spy 采样不到
   (该段为盲区), 所以 combo 的 MISS 图上解析段"看起来还是 cached_load_workbook:170 下
   一大块", 实际 wall time 已缩短。
3. **TP08 的 soffice 段缺失**: py-spy 只采主 python 进程, soffice 是其子进程,
   主进程阻塞在 wait 期间样本记为 errors(数百个)。
4. 采集用增强脚本是 recipe 原版 10KB enhance_workbook.py(从 recipe JSON 提取),
   保证 verify 检查的 Executive_Summary 等结构齐全, verify/summary 跑通(rc=0)。
