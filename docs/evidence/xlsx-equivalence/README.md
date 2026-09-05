# XLSX 优化产物一致性证据(equivalence evidence)

验证问题: 经过 disk-cache(磁盘缓存)与 speedups(Cython 加速)两层优化后, 产物与 stock 是否一致?
验证环境: j 机(920B), 镜像 `ubuntu-document-bench:xlsx-combo`(2026-09-05, 单容器内环境变量切换三种模式),
种子模板 `/opt/document-bench/xlsx/input/monthly_operations_template.xlsx`(100,001 行 × 25 列 / 2,501,211 格)。
复现: `docker run --rm -v <本目录>:/w -w /w ubuntu-document-bench:xlsx-combo bash /w/run_equiv.sh`(TP-07 链路另需 recipe 原版 enhance 脚本, 见 enh_cmp.sh)。

## 三层产物, 三种判定

### 第 1 层: 加载产物(内存对象树) — 完全一致

`fp.py` 对全部 250 万 Cell 逐格取指纹(值 repr / data_type / 完整 StyleArray 元组 /
评论文本+作者 / 超链接目标) + 表级元数据(行列/合并区/冻结/图表类型/数据校验/条件格式) +
defined_names + 外链数, 汇总 sha256:

| 路径 | TOTAL 指纹 | 原始输出 |
|---|---|---|
| stock(OPENPYXL_CACHE=0 OPENPYXL_SPEEDUPS=0) | `4a643dc1859ebebd…b0e2ff9` | fp_A.json |
| speedups only(MISS 冷解析) | 同上 | fp_B.json |
| 组合 MISS | 同上 | fp_C_miss.json |
| 组合 HIT(快照重建) | 同上 | fp_C_hit.json |

四路全同: 250 万格 × 7 维逐格一致。

### 第 2 层: 保存产物(openpyxl save, TP-07 路径) — 除固有易变成员外逐字节一致

`save.py` 对 zip 内全部成员取 md5(save_A1/A2/C.txt), `save_matrix.sh` 补全三路矩阵并
**显式证明缓存命中**(save_matrix.log):

- **stock 自身对照**(连续两次 save): 23 个成员恰 1 个不同 = `docProps/core.xml`,
  差异仅为 `<dcterms:modified>` 墙钟时间(02:56:32Z vs 02:57:23Z) — openpyxl 每次
  save 写当前时间, 与优化无关(对照组隔离了该变量)。
- **三路保存矩阵**(save_matrix.sh, 开 `OPENPYXL_CACHE_DEBUG=1`): 无缓存 stock /
  无缓存 speedups(MISS 解析) / **缓存命中 combo** 两两对比, 均仅 `docProps/core.xml`
  时间戳不同, 其余 22 个成员(含 123MB sheet1.xml/styles/charts/drawings)md5 全同。
  combo 侧 debug 日志 `[oxlcache] MISS+fill` → `[oxlcache] HIT … 3.908s` 直接证明
  save 消费的工作簿来自**缓存重建路径**(3.9s 为 HIT 重建时间特征, MISS 约 20s),
  排除"填充静默失败透传"的疑点。
- **真实 TP-07 增强链**(recipe 原版 enhance + 原子助手, enh_cmp.sh): 31 个成员仍仅
  `docProps/core.xml` 的 modified 时间不同; `<dcterms:created>`(模板原始创建时间
  2026-08-31T11:17:00Z)两路一致 — 缓存连创建时间戳都保真。

### 第 3 层: 最终交付物(LibreOffice 重算后 report.xlsx) — 不可逐字节判定, 业务校验背书

soffice 输出本身非确定(同一 stock 镜像两次全链重算, 指纹不同/大小差 1B, 2026-09-03 实测),
故该层等价判据为业务校验: verify_xlsx_enhanced.py 20+ 项 check + TP-15 六交付物断言 +
三份 JSON status==success, 2026-09-03 同窗口四组(stock/speedups/disk-cache/combo)
全部通过(Success 1/1, 1/1, 1/1, 2/2), 详见 docs/runlogs/xlsx-20260903/。

## 结论

| 产物 | 一致性 | 证据强度 |
|---|---|---|
| 内存对象树 | 逐格一致 | 四路 sha256 相同(250 万格 × 7 维) |
| openpyxl 保存文件 | 逐字节一致(除 save 固有时间戳) | 成员级 md5 + stock 对照组 |
| LibreOffice 重算后文件 | 不可判(非优化所致) | 四组业务校验全通过 |

远端副本: j 机 `~/yxy/document-bench/remote-workdir/xlsx/equivalence-check/`。
