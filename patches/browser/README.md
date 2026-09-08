# Browser patches

浏览器基准 (chromium + openclaw gateway + llama-server, docker provider) 的优化
产物, 按状态分档: `active/`(在用, 每个子目录一个优化点)、`archive/`(废弃留档)。

## active/

### jemalloc/ — 系统分配器替换 (源码编译 jemalloc 5.3.0, LD_PRELOAD)

jemalloc (`-O3 -mcpu=tsv110`, `--with-malloc-conf=narenas:2`) 以 `ENV LD_PRELOAD`
系统级替换 glibc malloc。作用对象 = node (openclaw gateway / agent-browser) /
llama-server / supervisord 等 glibc 分配进程; **Chromium 自带 PartitionAlloc 不受
LD_PRELOAD 影响**, 页面渲染主导耗时的场景预期收益有限。
删一个 ENV 即回退; 同窗 A/B 待跑, 结果回填 `active/jemalloc/README.md`。

## archive/

(暂无)
