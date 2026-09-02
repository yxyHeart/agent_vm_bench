# zlib-ng 系统压缩库替换 (E2E -0.89s)

单 Dockerfile 两阶段构建 (build 阶段装工具链+源码编译, runtime 阶段只拷 /opt/zlib-ng + LD_PRELOAD):

```bash
# 本目录放 zlib-ng-2.2.4.tar.gz (j 机 ~/pdfbuild/), 然后:
docker build -t ubuntu-document-bench:pdf-generic .
```

- zlib-ng 2.2.4, zlib-compat 模式 (soname/符号与 zlib 兼容, 上层零感知)
- 编译参数 `-O3 -mcpu=tsv110`, ARM NEON 向量化 (compare256/chunkset/slide_hash/adler32)
- 替换机制: `ENV LD_PRELOAD=/opt/zlib-ng/lib/libz.so.1`; 回退 = 删该 ENV
- 构建期断言: 进程内 libz 加载路径 + 压缩解压回环

实测 (METHOD.md 标准流程, 同窗 A/B, 各 15 任务, Success 100%):

| 阶段 | stock (系统 zlib) | zlib-ng | 差值 |
|------|----:|----:|----:|
| P01-inspect_prepare | 1,881ms | 1,688ms | -193ms |
| P02-build | 606ms | 571ms | -35ms |
| P03-process_publish | 8,695ms | 7,920ms | -775ms |
| P04-verify_deliver | 1,097ms | 1,045ms | -52ms |
| **合计** | **12.28s** | **11.22s** | **-1.06s (-8.6%)** |

探针归因 (libzcount.so): zlib 内部耗时 -58% (deflate -57% / inflate -62%, 1,465→620ms/任务)。
PNG 字节流不同但解码像素逐位一致 (P04 逐像素校验 100% 过)。
实验组配置: config/common/document-pdf-zng.yaml。
