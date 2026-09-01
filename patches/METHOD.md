# 优化层复现方法论：本地写 Dockerfile，远端构建运行

> 适用: `patches/{xlsx,pdf}/` 下的优化层——任何"在基准镜像上 COPY/注入若干文件"的加速层
> (xlsx: speedups / disk-cache / 组合; pdf: 同构的注入层均适用)。
> 模式: **本地仓库改代码 → scp 上机校验 → 远端构建镜像 → 远端跑基准 → 结果回填本地**。
> 实测记录(2026-09-01, 同日同窗口): stock 258.7s; speedups 218.2s(-15.7%); disk-cache 165.5s(-36.0%); 组合 143.1s(-44.7%)。

## 零. 全景

```text
本地 (Mac, 仓库)                      远端 (j 机, aarch64 构建宿主)
─────────────────                    ─────────────────────────────
patches/<域>/<层>/ (域=xlsx 或 pdf)            ~/run-<层>/            ← scp + md5 校验
  Dockerfile                            │ docker build
  注入文件(.py/.pth/.pyx)               ▼
                                     ubuntu-document-bench:<tag>
                                        │ bench-core --config(指定 image)
                                        ▼
                                     容器跑 recipe → E2E 数据
```

每一层只做一件事: 在基础镜像上 `COPY` 几个文件进 `dist-packages`。
recipe/容器规格/业务命令零改动——容器里每个 `python3` 启动时经 `.pth`
自动加载注入层。

## 一. 前置检查(远端)

```bash
ssh j 'docker images | grep 24.04-linuxarm64'                          # 基础镜像在位
ssh j 'source ~/yxy/document-bench/venv/bin/activate && cython --version'  # 仅 speedups 需要
ssh j 'ls ~/yxy/document-bench/build-gen/pyroot/include/python3.12/Python.h'  # 仅 speedups 编译需要
```

## 二. 同步代码上机(本地)

```bash
cd /Users/yxy/Desktop/agent_vm_bench
SCOPE=xlsx                 # 域: xlsx 或 pdf
LAYER=disk-cache           # 该域下的层目录名; speedups 额外带 build.sh
rm -rf /tmp/sync_layer && mkdir -p /tmp/sync_layer
cp patches/$SCOPE/$LAYER/* /tmp/sync_layer/
scp -r /tmp/sync_layer j:~/
ssh j "rm -rf ~/run-$LAYER && mv ~/sync_layer ~/run-$LAYER"
```

**一致性校验(必做)**——两边的 md5 逐一相等才算"跑的是仓库这份代码":

```bash
md5 -q patches/$SCOPE/$LAYER/*.py patches/$SCOPE/$LAYER/*.pth
ssh j "md5sum ~/run-$LAYER/*.py ~/run-$LAYER/*.pth | awk '{print \$1}'"
```

## 三. 远端构建镜像

```bash
# disk-cache(纯 Python 注入, 无编译): 一条 docker build
ssh j 'cd ~/run-disk-cache && docker build -t ubuntu-document-bench:disk-cache .'

# speedups(需编译): cython → gcc → docker build
ssh j 'cd ~/run-speedups && source ~/yxy/document-bench/venv/bin/activate && \
  PYINC=$HOME/yxy/document-bench/build-gen/pyroot/include/python3.12 bash build.sh'
# build.sh 产物: openpyxl_speedups.cpython-312-aarch64-linux-gnu.so + 镜像 speedups
# 注: 头文件仅编译期使用, .so 链接的是镜像自带发行版 libpython3.12 ABI

# 组合镜像(两层的 Dockerfile 叠加, 见 patches/xlsx/README.md)
```

## 四. 生效验证(必做, 防"构建成功但没注入")

```bash
ssh j 'docker run --rm ubuntu-document-bench:disk-cache bash -c "
python3 -c \"from openpyxl import load_workbook; print(load_workbook.__name__)\"
"'
# 预期: cached_load_workbook (stock 是 load_workbook)

ssh j 'docker run --rm ubuntu-document-bench:speedups python3 -c "
import openpyxl.worksheet._reader as r
print(type(r.WorkSheetParser.parse_cell).__name__)"'
# 预期: cython_function_or_method (stock 是 function)
```

功能验证(disk-cache 的命中链, ~1 分钟):

```bash
ssh j 'docker run --rm -v /tmp:/h ubuntu-document-bench:disk-cache bash -c "
export OPENPYXL_CACHE_DEBUG=1
python3 /h/dump_wb.py /opt/document-bench/xlsx/input/monthly_operations_template.xlsx   # MISS ~25s
python3 /h/dump_wb.py /opt/document-bench/xlsx/input/monthly_operations_template.xlsx   # HIT ~4s, md5 相同
"'
```

正确性基线(逐格 md5, 开/关对照, ~10 分钟):

```bash
ssh j 'docker run --rm -v /tmp:/h ubuntu-document-bench:<tag> sh -c "
python3 /h/dump_wb.py /opt/document-bench/xlsx/input/monthly_operations_template.xlsx       # 开
OPENPYXL_CACHE=0 OPENPYXL_SPEEDUPS=0 python3 /h/dump_wb.py /opt/document-bench/xlsx/input/monthly_operations_template.xlsx  # 关
"'
# 两行 md5 必须一致 (模板基准指纹 fcb714e2c909329001c81284c425b035)
```

## 五. 端到端基准

配置文件决定容器镜像(`docker.image` 字段), 每个实验组一个 yaml:

```bash
ssh j
cd ~/yxy/document-bench && source venv/bin/activate

# 5a 清残留沙箱
bench-core --provider docker --config config/common/document-xlsx-<tag>.yaml --cleanup

# 5b 实验组
bench-core --provider docker --config config/common/document-xlsx-<tag>.yaml -n 1 \
  2>&1 | tee /tmp/e2e_<tag>.log

# 5c stock 对照(同日同窗口, 排除环境漂移)
bench-core --provider docker --config config/common/document-xlsx.yaml -n 1

# 5d 逐调用数据(CALLTIMINGS JSON)
grep -o "\[CALLTIMINGS\].*" /tmp/e2e_<tag>.log | head -1
```

配置生成模板(从 stock 配置派生):

```bash
ssh j 'cd ~/yxy/document-bench && sed \
  -e "s|ubuntu-document-bench:24.04-linuxarm64|ubuntu-document-bench:<tag>|" \
  -e "s|filename_prefix: \"document_xlsx_bench\"|filename_prefix: \"document_xlsx_<tag>_bench\"|" \
  config/common/document-xlsx.yaml > config/common/document-xlsx-<tag>.yaml'
```

已有配置: `document-xlsx-speedups.yaml` / `document-xlsx-disk-cache.yaml` / `document-xlsx-combo.yaml`(组合)。

关键读数: `Success Rate: 100%` + `Avg Latency`。Success 100% 不只是退出码——
verify 脚本任一 check 失败即任务失败, 它同时证明业务语义没被破坏。

## 六. 结果回填本地

```bash
# 数据写进报告(docs/xlsx-generic-stack-report.md), 逐调用对照表更新
# 远端临时目录清理:
ssh j "rm -rf ~/run-<layer>"
# 本地提交(分支推 fork):
git add patches/... docs/... config/... && git commit -m "..." && git push myfork <branch>:main
```

## 七. 实测基线表(2026-09-01)

| 组 | image tag | E2E | vs stock |
|----|-----------|----:|----:|
| stock | `24.04-linuxarm64` | 258.7s | — |
| speedups | `speedups` | 218.2s | -15.7% |
| disk-cache | `disk-cache` | 165.5s | -36.0% |
| 组合 | `xlsx-combo` | 143.1s | -44.7% |

微基准参考: 冷加载 22.3s(stock) / 17.9s(speedups) / 3.9s(缓存 HIT); 重算形态 HIT 4.1s。

## 八. 常见坑

| 症状 | 原因 | 解法 |
|------|------|------|
| 构建成功但 `type(parse_cell)` 仍是 function | 组合镜像里 `oxlcache.pth` 先 import 了 openpyxl, speedups 的懒 finder 永不触发 | 已修: bootstrap 检测 openpyxl 已在 sys.modules 则立即 patch; 旧 .so 需重建 |
| `Python.h: No such file or directory` | PYINC 默认相对路径在 j 机不成立 | `PYINC=$HOME/yxy/document-bench/build-gen/pyroot/include/python3.12 bash build.sh` |
| 缓存永不命中 | 每次实验前 `--cleanup` 重建容器——缓存目录 `/tmp/oxlcache` 在容器内, 容器销毁即失效属预期 | 同容器内连续调用才体现 HIT(基准内 TP-05/09/10/13/14 均命中) |
| 结果漂移 | 环境噪声 | stock 对照必须同日同窗口跑; 报告数字以 A/B 差为准 |
