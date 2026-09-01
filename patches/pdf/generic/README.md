# PDF 通用底层优化 — 构建配方与工具

镜像链 (顺序构建, 上一层是下一层的基底):

```
ubuntu-document-bench:24.04-linuxarm64   vanilla 基准 (对照零点)
        │  Dockerfile.toolchain          + gcc/cmake/ninja 编译环境
        ▼
pdf-build:base
        │  Dockerfile.build-libs         源码编译 zlib-ng(-O3 -mcpu=tsv110) → /out/
        ▼
pdf-build:native-libs
        │  Dockerfile.runtime            拷 /out/zlib-ng → /opt + pypdf 协议补丁 + 断言
        ▼
ubuntu-document-bench:pdf-generic        生产镜像 (benchmark 使用)
```

## 文件

| 文件 | 用途 |
|------|------|
| `Dockerfile.toolchain` | 构建环境层 |
| `Dockerfile.build-libs` | zlib-ng 编译层 |
| `Dockerfile.runtime` | 生产镜像层 (`ENV LD_PRELOAD=/opt/zlib-ng/lib/libz.so.1`) |
| `runtime-setup.sh` | pypdf 协议继承移除 (2 处 sed) + 双断言 (metaclass / libz 加载路径) |
| `zcount.c` | zlib 调用探针源码: LD_PRELOAD 拦截 deflate/inflate 计数+计时; 日志按 pid+starttime 命名, 防容器 pid 复用覆盖 |
| `Dockerfile.probe` | 计量镜像 (vanilla+探针; ARG VARIANT 可切 zlib-ng NEON/SVE) |
| `collect-exact-bench.sh` | 跑 bench 并完整收割探针日志 (detect 模式, 容器不销毁) |

## 用法

```bash
# 生产镜像
docker build -t pdf-build:base -f Dockerfile.toolchain .
docker build -t pdf-build:native-libs -f Dockerfile.build-libs .
docker build -t ubuntu-document-bench:pdf-generic -f Dockerfile.runtime .

# zlib 三变体计量 (需先构建 zng-sve 对照库, 见 archive/Dockerfile.zng-sve)
gcc -O2 -shared -fPIC -o libzcount.so zcount.c -ldl
docker build -t bench-z:orig -f Dockerfile.probe .
docker build --build-arg VARIANT=base --build-arg LIBZ=:/opt/zlib/lib/libz.so.1 -t bench-z:ng -f Dockerfile.probe .
docker build --build-arg VARIANT=sve --build-arg LIBZ=:/opt/zlib/lib/libz.so.1 -t bench-z:sve -f Dockerfile.probe .
```

上游源码包 (zlib-ng-2.2.4.tar.gz 等) 在 j 机 `~/pdfbuild/`, 不入 git。
实验结论详见 `docs/pdf-generic-optimization-roadmap.md` 与 `docs/pdf-final-report.md`。
