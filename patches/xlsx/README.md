# XLSX patches

XLSX 文档基准的全部优化产物, 按状态分档: `active/`(在用)、`archive/`(废弃留档)、`tools/`(采集工具)。

**复现方法论见 `../METHOD.md`**(patches 通用: 本地写 Dockerfile → 远端构建运行, 含实测基线表与常见坑)。

**推荐组合 = active/ 下两个方案叠加**(`Dockerfile.combo`, 见下): E2E **257.5s → 143.0s (-44.5%, 2 任务均值; 冷对冷 153.0s/-40.6%)**, Success 2/2(2026-09-03 同窗口四组重测, 原始日志 `docs/runlogs/xlsx-20260903/`)。

## active/ — 当前在用

### speedups/ — openpyxl 原生加速扩展

发行版 CPython 原样, Cython 编译的 openpyxl 加速层, 优化**每次解析本身**。

- **机制**: `bind_cells` 融合原生循环(四层 Python 调用链内联为一个 C 循环, 每格中间 dict/方法调用/三次子树扫描消失) + `parse_cell` 编译版(覆盖 read_only 流式路径) + 解析期 GC 守卫
- **单独实测**: 冷加载 22.3→17.9s(-19.6%, 手测); 单独 E2E 257.5→217.0s(-15.7%, 2026-09-03)
- **安全防线**: 版本门精确 `openpyxl==3.1.5`; `OPENPYXL_SPEEDUPS=0` 一键关闭; 异常回退 stock; 250 万格 md5 与 stock 逐格一致
- **文件**: `openpyxl_speedups.pyx`(Cython 源) / `oxlspeed_bootstrap.py`(懒加载注入钩子, 已处理与其他 .pth 的顺序竞争: openpyxl 已被导入则立即 patch) / `oxlspeed.pth` / `Dockerfile` / `build.sh`

### disk-cache/ — 多次读磁盘缓存

同一文件的重复 `load_workbook` 只解析一次, 之后从快照重建。

- **机制**: 内容指纹做键(首尾 4MB md5+大小, 同内容不同路径共享、改写自动失效); MISS 正常解析后把"无格工作簿壳+紧凑格表"pickle 落盘; HIT 直接反序列化重建(直填槽位), 跳过全部 XML 解析; read_only/非文件/失败一律透传
- **单独实测**(无 speedups): E2E 257.5→170.6s(-33.7%, 2026-09-03)
- **与 speedups 正交组合**: 缓存救"重复解析"(MISS 解析走加速 reader, HIT 完全不碰 XML), speedups 救"每次解析成本"
- **开关**: `OPENPYXL_CACHE=0` / `OPENPYXL_CACHE_DIR` / `OPENPYXL_CACHE_DEBUG`
- **文件**: `openpyxl_cache.py` / `oxlcache.pth` / `Dockerfile`

### 组合镜像(推荐)

Dockerfile: [`Dockerfile.combo`](Dockerfile.combo) — **单命令构建**,编译(.so)在 builder 阶段内完成(apt cython3 + gcc + python3.12-dev),无需宿主工具链、无需手工拷文件:

```bash
docker build --network=host -t ubuntu-document-bench:xlsx-combo \
  -f patches/xlsx/active/Dockerfile.combo patches/xlsx/active/
# --network=host: 容器默认网桥无 DNS 时 apt 需走宿主网络(920B 实测必须)
# 前提: 基础镜像 ubuntu-document-bench:24.04-linuxarm64 已在本地
```

镜像内容 = 基础镜像 + 两方案共 5 个注入文件(speedups 3 + cache 2)。
已验证与分步构建的参考镜像等价: E2E 143.7s vs 143.0s(2 任务均值, 2026-09-04)。

组合 E2E: **257.5 → 143.0s(-44.5%, 均值; 冷对冷 153.0s/-40.6%)**, Success 2/2; 重复加载调用降至 5~9s(命中重建 ~4s)。
配置: `config/common/document-xlsx-combo.yaml`。

## archive/ — 已废弃(留档, 勿部署)

### workload-aware-final/ — 大表懒物化层 v4 末态(已放弃)

按结构识别"大而简单的表"改变解析/物化/写出行为的整层路线, 经评估不符合零感知约束而放弃;
曾达 259→57.6s(-77.7%)。只保留 v4 最终版(openpyxl_cache.py + .pth + Dockerfile + README),
v1-v3 中间轮次与调试遗留已清; 可继承部分(磁盘缓存/GC/直填)已剥离进 active/。详见其 README。

## tools/ — 一次性采集工具(留档)

| 文件 | 说明 |
|------|------|
| `xlsx_flame_all.py` | 按 recipe 逐步生成 py-spy 火焰图(产物见 `docs/flames/xlsx_steps*/`) |

路径硬编码(j 机容器内 `/tmp` 工作区), 仅用于复现当时的采集。(早期用于重采失败步骤的
`xlsx_flame_redo.py` 已删: 产物 step07/13/14 均已落库, 无复用价值。)

## 复现

```bash
# 组合镜像 = 一条命令(编译内置于 builder 阶段, 见上节 Dockerfile.combo)
docker build --network=host -t ubuntu-document-bench:xlsx-combo \
  -f patches/xlsx/active/Dockerfile.combo patches/xlsx/active/
bench-core --provider docker --config config/common/document-xlsx-combo.yaml -n 1   # 143.0s (均值口径)
bench-core --provider docker --config config/common/document-xlsx-speedups.yaml -n 1 # 217.0s (仅 speedups)
```

报告: `docs/xlsx-generic-stack-report.md`(通用栈) / `docs/xlsx-optimization-report.md`(历史四轮)
