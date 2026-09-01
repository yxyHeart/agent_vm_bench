# 优化点测试流程（方法论）

> 本文描述**测试一个优化点的标准流程**: 本机写 patch → 远程服务器构建 → 远程跑基准 → 结果回填。
> 与具体优化无关——xlsx / pdf / 任何新场景的优化点都走同一条流程。
> 各场景的层说明见 `patches/<场景>/README.md`, 实测数据见各自报告(docs/)。

## 流程总览

```text
┌─────────── 本机 (仓库所在) ───────────┐      ┌─────────── 远程测试机 ───────────────┐
│ 1. 写优化层                            │      │                                      │
│    patches/<场景>/<层名>/              │ scp  │ 3. 构建实验镜像                       │
│      Dockerfile (基础镜像+COPY 文件)   │ ───▶ │    docker build -t <base>:<tag> .    │
│      注入文件 (.py/.pth/.so/...)       │ md5  │                                      │
│      build.sh (若需编译)               │ 校验 │ 4. 验证注入生效                       │
│                                      │      │    (不信任"build 成功")               │
│ 2. 生成本实验组配置                    │      │                                      │
│    config/common/*-<tag>.yaml          │      │ 5. 跑 E2E: 实验组 + stock 同窗对照    │
│                                      │      │                                      │
│ 7. 回填: 报告/数据/提交推送             │ ◀─── │ 6. 产出: Success率 / Avg Latency /    │
└──────────────────────────────────────┘      │    per-call 计时 (CALLTIMINGS)        │
                                              └──────────────────────────────────────┘
```

核心原则:

- **优化只通过"镜像层"进入测试环境**——基础镜像上一个 Dockerfile COPY 若干文件, recipe/容器规格/业务命令零改动; patch 永远不直接改测试机上的文件。
- **每一步有明确的"通过判据"**, 不通过就停下排查, 不带病进入下一步。
- **任何性能结论必须来自同日同窗口的 A/B**(实验组 vs stock 对照), 单边数字不作数。

## Step 1 本机: 写优化层

目录约定:

```text
patches/<场景>/<层名>/
├── Dockerfile      # FROM <基础镜像> + COPY 注入文件(必选)
├── <注入文件>      # .py/.pth/.so/.pyx 等, 按层需要
└── build.sh        # 仅当需要编译(cython/gcc); 产物 + docker build 一步完成
```

Dockerfile 模板(注入型优化层的唯一形态):

```dockerfile
FROM <基础镜像>
COPY <文件...> <目标路径, 通常 python site-packages>
```

注意:

- 层要**自带关闭开关**(环境变量), 保证随时能回退 stock 行为做对照。
- 若 patch openpyxl/pypdf 等库内部, 加**版本门**精确锁版本, 版本不符自动不启用。
- 注入钩子用 `.pth`(每个 python3 启动自动加载), 多个 .pth 共存时注意**导入顺序竞争**
  (若 A 钩子先 import 了目标库, B 的懒 finder 永不触发——B 需处理"目标库已在 sys.modules"
  的情形, 见 patches/xlsx/active/speedups/oxlspeed_bootstrap.py)。

## Step 2 本机: 生成实验组配置

从 stock 配置派生, 只改两处(image → 实验镜像 tag, filename_prefix → 实验组名):

```bash
ssh 远程 'sed \
  -e "s|<基础镜像>|<基础镜像>:<tag>|" \
  -e "s|filename_prefix: \"<stock前缀>\"|filename_prefix: \"<stock前缀>_<tag>\"|" \
  <stock配置>.yaml > <stock配置>-<tag>.yaml'
```

配置是实验组的唯一入口: bench-core `--config` 选配置, 配置里 `docker.image` 决定容器跑在哪个镜像上。取回本地入库。

## Step 3 同步上机 + 一致性校验

```bash
cd <本地仓库>
rm -rf /tmp/sync_layer && mkdir -p /tmp/sync_layer
cp patches/<场景>/<层名>/* /tmp/sync_layer/
scp -r /tmp/sync_layer 远程:~/
ssh 远程 "rm -rf ~/run-<层名> && mv ~/sync_layer ~/run-<层名>"
```

**md5 双向校验(必做)**——保证"远端跑的就是仓库这份代码":

```bash
md5 -q patches/<场景>/<层名>/<文件>...          # 本地
ssh 远程 "md5sum ~/run-<层名>/<文件>... | awk '{print \$1}'"   # 远端, 逐一相等
```

## Step 4 远程: 构建实验镜像

```bash
# 纯文件注入层(无编译):
ssh 远程 'cd ~/run-<层名> && docker build -t <基础镜像>:<tag> .'

# 需编译层(cython 等): build.sh 内部完成 编译→docker build
ssh 远程 'cd ~/run-<层名> && <提供编译工具的 env> bash build.sh'
```

通过判据: `Successfully tagged <基础镜像>:<tag>`。

## Step 5 远程: 验证注入生效(不信任 build 成功)

构建成功 ≠ 优化生效。逐层有各自的"生效指纹", 用一次性容器直接验证:

```bash
ssh 远程 'docker run --rm <镜像> python3 -c "<检查项>"'
```

检查项示例(按层性质选):

| 层性质 | 检查项 | stock 值 | 生效值 |
|---|---|---|---|
| monkey-patch 函数 | `type(<被替换函数>).__name__` | `function` | `cython_function_or_method` / wrapper 名 |
| 包装 API | `<API>.__name__` | 原名 | wrapper 名 |
| 缓存层 | 同文件两次加载, 第二次 debug 日志 | 无 | `HIT ... N s` |

再补**正确性基线**(成本 ~10 分钟, 强烈建议): 被优化库的输出指纹(如逐格 md5), 实验组 vs `关闭开关` 对照, 必须逐字节一致。

## Step 6 远程: 跑端到端基准

```bash
ssh 远程
cd <基准仓库> && source venv/bin/activate

# 6a 清残留沙箱
bench-core --provider docker --config <实验组配置> --cleanup

# 6b 实验组
bench-core --provider docker --config <实验组配置> -n 1 2>&1 | tee /tmp/e2e_<tag>.log

# 6c stock 对照(同日同窗口, 不可省——排除环境漂移)
bench-core --provider docker --config <stock配置> -n 1

# 6d per-call 计时(逐调用归因)
grep -o "\[CALLTIMINGS\].*" /tmp/e2e_<tag>.log | head -1
```

通过判据(两个都要):

1. `Success Rate: 100%` —— 不只是退出码, verify 脚本任一业务 check 失败即任务失败, 它同时证明语义未破坏;
2. 实验组 Avg Latency 明显低于同窗 stock(差值小于噪声时结论记"持平", 不硬贴收益)。

## Step 7 回填本机

```bash
# 数据写进该场景的报告(docs/<场景>-*.md): 总表 + 逐调用对照 + 归因
# 远端临时目录按需清理(保留亦可, 便于考古重跑):
ssh 远程 "rm -rf ~/run-<层名>"
# 本地提交推送:
git add patches/... config/... docs/... && git commit -m "..." && git push <remote> <branch>:main
```

## 附: 常见坑(按流程步骤)

| 步骤 | 症状 | 原因与解法 |
|---|---|---|
| 4 | `Python.h: No such file` | 编译头文件路径不对, 用环境变量显式指定 PYINC(仅编译期需要, .so 链接镜像自带 libpython) |
| 5 | build 成功但 type 检查仍是 stock | 多 .pth 导入顺序竞争: 某钩子先 import 目标库, 懒 finder 永不触发; 钩子需处理"已导入则立即 patch" |
| 5 | 缓存类优化"永不命中" | 缓存落在容器内 `/tmp`, `--cleanup` 销毁容器即失效——属预期; 命中收益体现在同一任务内的重复调用 |
| 6 | 数字漂移 | stock 对照未同日同窗跑; 结论只认 A/B 差值 |
| 6 | 容器规格不符 | 配置里 cpu_limit/memory_limit 决定 `docker run --cpus/-m`, 别在测试机上手工 docker run 跑性能数据 |
