# zlib-ng 系统压缩库替换 (E2E -0.89s)

镜像链顺序构建 (上层是下层基底):
```
ubuntu-document-bench:24.04-linuxarm64   vanilla 基准
   │ Dockerfile.toolchain        + gcc/cmake/ninja
   ▼ pdf-build:base
   │ Dockerfile.build-libs       源码编译 zlib-ng 2.2.4 (zlib-compat, -O3 -mcpu=tsv110) → /out/
   ▼ pdf-build:native-libs
   │ Dockerfile.runtime          拷 /out/zlib-ng → /opt + ENV LD_PRELOAD + 协议补丁断言
   ▼ ubuntu-document-bench:pdf-generic      生产镜像
```

zlib 内部耗时 -58% (deflate -57% / inflate -62%); PNG 字节流不同但解码像素逐位一致。
源码包 zlib-ng-2.2.4.tar.gz 在 j 机 ~/pdfbuild/, 不入 git。
