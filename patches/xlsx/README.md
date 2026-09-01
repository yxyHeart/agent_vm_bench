# XLSX patches

XLSX 文档基准的全部优化产物, 按状态分档: `active/`(在用)、`archive/`(废弃留档)、`tools/`(采集工具)。

## active/ — 当前推荐方案

### speedups/ — openpyxl 原生加速扩展(唯一在用)

发行版 CPython 原样, 仅注入 Cython 编译的 openpyxl 加速层。

- **实测**: 冷加载 22.3→17.9s(-19.6%); E2E 258.3→217.9s(-15.4%), Success 100%
- **机制**: `bind_cells` 融合原生循环(四层 Python 调用链内联为一个 C 循环, 每格中间 dict/方法调用/三次子树扫描消失) + `parse_cell` 编译版(覆盖 read_only 流式路径) + 解析期 GC 守卫(单项 -3.9s)
- **安全防线**: 版本门精确 `openpyxl==3.1.5`; `OPENPYXL_SPEEDUPS=0` 一键关闭; 任何异常回退 stock; 250 万格 md5 三形态与 stock 一致
- **文件**:
  - `openpyxl_speedups.pyx` — Cython 源(核心)
  - `oxlspeed_bootstrap.py` — 懒加载注入钩子(openpyxl 导入瞬间替换; 不碰 openpyxl 的进程零开销)
  - `oxlspeed.pth` — .pth 注入
  - `Dockerfile` — 镜像层(基础镜像 + 三个文件进 dist-packages)
  - `build.sh` — 宿主编译扩展 + 构建镜像

```bash
bash patches/xlsx/active/speedups/build.sh    # 产出 ubuntu-document-bench:speedups
bench-core --provider docker --config config/common/document-xlsx-speedups.yaml -n 1
```

报告: `docs/xlsx-generic-stack-report.md`

## archive/ — 已废弃(留档, 勿部署)

### workload-aware-v1-v4/ — 工作负载感知加速层

v1→v4 四轮演进的注入层(单一 `openpyxl_cache.py` 逐步叠加机制), 曾达
259s→57.6s(-77.7%), **后被否决**: 其机制依赖对工作簿结构的感知
(按内容指纹的磁盘缓存/大表懒物化/存盘字节直通/按需物化), 对新流程存在
行为影响, 不符合"零 workload 感知"约束。产物语义正确性已充分验证
(逐格 md5 一致), 全部数据与结论见 `docs/xlsx-optimization-report.md`。

| 文件 | 说明 |
|------|------|
| `openpyxl_cache.py` | v4 最终版: 磁盘缓存 + GC 守卫 + 直填槽位 + 懒物化 + 流式遍历 + 存盘直通 |
| `oxlcache.pth` | 其注入钩子 |
| `Dockerfile.cached` / `.xlsx-v2/v3/v4` | 各轮镜像层(均 COPY 上述两文件, v2 起加 lxml wheel) |
| `sitecustomize.py` | ❌ 失效调试遗留: v1 早期用于打印注入轨迹的调试钩子, 被 oxlcache.pth 取代后未删, 与任何现存镜像/配置无引用关系 |

注意: v2 起的 Dockerfile 依赖镜像构建目录里有 `lxml-6.1.2-cp312-...whl`
(离线安装), 该 wheel 不在仓库; 且 `Dockerfile.xlsx-v3/v4` 内容与 v2 完全
相同(历史原因, 实际靠 openpyxl_cache.py 版本区分轮次)。

## tools/ — 一次性采集工具(留档)

| 文件 | 说明 |
|------|------|
| `xlsx_flame_all.py` | 按 recipe 逐步生成 py-spy 火焰图(产物见 `docs/flames/xlsx_steps*/`) |
| `xlsx_flame_redo.py` | 重采早期失败的步骤(7/13/14) |

两者路径硬编码(j 机容器内 `/tmp` 工作区), 仅用于复现当时的采集, 不参与
任何构建/部署。
