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

实测: zlib 内部耗时 -58% (deflate -57% / inflate -62%, 1,465→620ms/任务);
PNG 字节流不同但解码像素逐位一致 (P04 逐像素校验 100% 过)。
与 pypdf-protocol-patch 独立, 叠加方式见上级 README。
