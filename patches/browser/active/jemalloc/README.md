# jemalloc 系统分配器替换 (源码编译, LD_PRELOAD)

jemalloc 5.3.0 源码编译 (`-O3 -mcpu=tsv110`, `--with-malloc-conf=narenas:2`),
以 `ENV LD_PRELOAD` 系统级替换容器内 glibc malloc, 上层零感知。

## 动机与作用边界

browser 容器 (chromium + openclaw + llama-server, supervisor 托管) 内的常驻服务
除 Chromium 外均为 glibc malloc 使用者:

| 进程 | 分配器 | 受本层影响 |
|---|---|---|
| openclaw gateway / agent-browser (node) | glibc | 是 |
| llama-server | glibc | 是 |
| supervisord (python) | glibc | 是 |
| chromium | 自带 PartitionAlloc (静态覆盖 malloc) | **否** |

node 网关 (agentic 业务循环, 高频小对象) 与 llama-server (推理 tensor 缓冲)
在 2 vCPU 限核容器内并发分配, glibc 单 arena 锁竞争 + 碎片是候选瓶颈;
jemalloc 的 per-thread cache / 多 arena / 碎片治理可能改善。
**Chromium 自带 PartitionAlloc, LD_PRELOAD 不改变其内部分配** —— 本层 A/B 结论
只反映 node/llama-server/supervisord 等进程的分配器差异, 若页面渲染主导耗时,
预期收益有限 (这本身也是一次有价值的边界测定)。

## 构建

```bash
# 本目录放源码包 (j 机可达 github), 校验后构建:
wget https://github.com/jemalloc/jemalloc/releases/download/5.3.0/jemalloc-5.3.0.tar.bz2
md5sum    jemalloc-5.3.0.tar.bz2   # 预期 09a8328574dab22a7df848eae6dbbf53
sha256sum jemalloc-5.3.0.tar.bz2   # 预期 2db82d1e7119df3e71b7640219b6dfe84789bc0537983c3b7ac4f7189aecfeaa
docker build -t ubuntu-openclaw-chromium:24.04-arm64-jemalloc .
```

- `narenas:2` 预置进默认 conf, 对齐容器 2 vCPU 规格; 运行时可用 `MALLOC_CONF`
  环境变量覆盖 (如 `MALLOC_CONF=narenas:4,dirty_decay_ms:5000`)。
- 构建期断言 (RUN 内): sh 进程 maps 加载 jemalloc + supervisord/node/chromium
  三运行时可正常启动 (镜像无 python3, 故用 shell 断言)。

## 生效指纹 (不信任 build 成功)

```bash
# 任一命令进程内 jemalloc 已加载:
docker run --rm ubuntu-openclaw-chromium:24.04-arm64-jemalloc \
  sh -c 'grep libjemalloc /proc/self/maps'

# 容器内常驻服务 (openclaw gateway) 真实用上 jemalloc —— 关键验证:
docker run --rm -d --name jm-verify ubuntu-openclaw-chromium:24.04-arm64-jemalloc
docker exec jm-verify sh -c \
  "for p in \$(ls /proc | grep -E '^[0-9]+\$'); do grep -q libjemalloc /proc/\$p/maps 2>/dev/null && echo \$p: \$(cat /proc/\$p/comm); done"
docker rm -f jm-verify
```

预期: node / supervisord / llama-server 相关进程逐个列出。

## 关闭开关 / 回退

- 一次性容器即时回退: `docker run -e LD_PRELOAD= ...` (清空 ENV 即恢复 glibc)。
- bench-core A/B 对照: 切回 stock 配置 `config/common/browser.yaml`
  (实验组入口 = `config/common/browser-jemalloc.yaml`, 仅 image 与
  filename_prefix 两处差异, 见 METHOD.md Step 2)。

## 实测

待同窗 A/B (METHOD.md Step 5-7): 先 `--create-only` 冒烟 (ready 探针过 = 三服务
在 jemalloc 下正常监听), 再 jemalloc vs stock 同窗交替对照。结果回填本节。
