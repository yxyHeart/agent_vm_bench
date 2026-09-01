# XLSX patches

XLSX 文档基准的全部优化产物, 按状态分档: `active/`(在用)、`archive/`(废弃留档)、`tools/`(采集工具)。

**推荐组合 = active/ 下两个方案叠加**(`Dockerfile.combo` 形态, 见下): E2E **258.3s → 143.1s (-44.5%), Success 100%**。

## active/ — 当前在用

### speedups/ — openpyxl 原生加速扩展

发行版 CPython 原样, Cython 编译的 openpyxl 加速层, 优化**每次解析本身**。

- **机制**: `bind_cells` 融合原生循环(四层 Python 调用链内联为一个 C 循环, 每格中间 dict/方法调用/三次子树扫描消失) + `parse_cell` 编译版(覆盖 read_only 流式路径) + 解析期 GC 守卫
- **单独实测**: 冷加载 22.3→17.9s(-19.6%); 单独 E2E 258.3→217.9s(-15.4%)
- **安全防线**: 版本门精确 `openpyxl==3.1.5`; `OPENPYXL_SPEEDUPS=0` 一键关闭; 异常回退 stock; 250 万格 md5 与 stock 逐格一致
- **文件**: `openpyxl_speedups.pyx`(Cython 源) / `oxlspeed_bootstrap.py`(懒加载注入钩子, 已处理与其他 .pth 的顺序竞争: openpyxl 已被导入则立即 patch) / `oxlspeed.pth` / `Dockerfile` / `build.sh`

### disk-cache/ — 多次读磁盘缓存

同一文件的重复 `load_workbook` 只解析一次, 之后从快照重建。

- **机制**: 内容指纹做键(首尾 4MB md5+大小, 同内容不同路径共享、改写自动失效); MISS 正常解析后把"无格工作簿壳+紧凑格表"pickle 落盘; HIT 直接反序列化重建(直填槽位), 跳过全部 XML 解析; read_only/非文件/失败一律透传
- **单独实测**(无 speedups): E2E 259→174.9s(-33%)
- **与 speedups 正交组合**: 缓存救"重复解析"(MISS 解析走加速 reader, HIT 完全不碰 XML), speedups 救"每次解析成本"
- **开关**: `OPENPYXL_CACHE=0` / `OPENPYXL_CACHE_DIR` / `OPENPYXL_CACHE_DEBUG`
- **文件**: `openpyxl_cache.py` / `oxlcache.pth` / `Dockerfile`

### 组合镜像(推荐)

```dockerfile
FROM ubuntu-document-bench:24.04-linuxarm64
COPY openpyxl_speedups.cpython-312-aarch64-linux-gnu.so oxlspeed_bootstrap.py oxlspeed.pth \
     /usr/local/lib/python3.12/dist-packages/
COPY openpyxl_cache.py oxlcache.pth /usr/local/lib/python3.12/dist-packages/
```

组合 E2E: **258.3 → 143.1s(-44.5%)**, Success 100%; 重复加载调用降至 5~9s(命中重建 ~4s)。
配置: `config/common/document-xlsx-combo.yaml`。

## archive/ — 已废弃(留档, 勿部署)

### workload-aware-v1-v4/ — 大表懒物化层(已放弃)

v3/v4 的核心机制——按结构识别"大而简单的表"、只解析头尾、按需物化、存盘字节直通、窗口物化——**全部依赖对工作簿结构的感知, 对新流程存在行为影响, 已放弃**(经评估保留的只有磁盘缓存, 已剥离为 active/disk-cache)。此目录是 v4 末态整体留档(含缓存+GC+直填+懒物化的纠缠实现), 曾达 259→57.6s(-77.7%), 数据见 `docs/xlsx-optimization-report.md`。

| 文件 | 说明 |
|------|------|
| `openpyxl_cache.py` | v4 末态(缓存+懒物化纠缠版, 勿用——纯缓存请取 active/disk-cache) |
| `oxlcache.pth` | 其注入钩子 |
| `Dockerfile.cached` / `.xlsx-v2/v3/v4` | 各轮镜像层(v2 起依赖构建目录里的 lxml wheel, 不在仓库; v3/v4 内容与 v2 相同) |
| `sitecustomize.py` | v1 早期调试钩, 失效遗留, 无引用 |

## tools/ — 一次性采集工具(留档)

| 文件 | 说明 |
|------|------|
| `xlsx_flame_all.py` | 按 recipe 逐步生成 py-spy 火焰图(产物见 `docs/flames/xlsx_steps*/`) |
| `xlsx_flame_redo.py` | 重采早期失败的步骤(7/13/14) |

路径硬编码(j 机容器内 `/tmp` 工作区), 仅用于复现当时的采集。

## 复现

```bash
# speedups 扩展编译(宿主需 cython + python3.12 头文件)
bash patches/xlsx/active/speedups/build.sh
# 组合镜像 = 基础镜像 + 两方案共 5 个文件(见上 Dockerfile)
bench-core --provider docker --config config/common/document-xlsx-combo.yaml -n 1   # 143.1s
bench-core --provider docker --config config/common/document-xlsx-speedups.yaml -n 1 # 217.9s (仅 speedups)
```

报告: `docs/xlsx-generic-stack-report.md`(通用栈) / `docs/xlsx-optimization-report.md`(历史四轮)
