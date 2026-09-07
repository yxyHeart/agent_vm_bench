# 生产镜像: browser 基础镜像 + 源码编译 jemalloc (LD_PRELOAD 系统级替换 glibc malloc)
# 构建上下文 = 本目录, 需放 jemalloc-5.3.0.tar.bz2 源码包:
#   wget https://github.com/jemalloc/jemalloc/releases/download/5.3.0/jemalloc-5.3.0.tar.bz2
# docker build -t ubuntu-openclaw-chromium:24.04-arm64-jemalloc .

FROM ubuntu-openclaw-chromium:24.04-arm64 AS build
RUN sed -i "s|ports.ubuntu.com/ubuntu-ports|repo.huaweicloud.com/ubuntu-ports|g" /etc/apt/sources.list.d/ubuntu.sources 2>/dev/null || true; \
    apt-get update && apt-get install -y --no-install-recommends build-essential bzip2 && rm -rf /var/lib/apt/lists/*
COPY jemalloc-5.3.0.tar.bz2 /src/
RUN cd /src && tar xf jemalloc-5.3.0.tar.bz2 && cd jemalloc-5.3.0 && \
    ./configure --prefix=/opt/jemalloc CFLAGS="-O3 -mcpu=tsv110" \
        --with-malloc-conf=narenas:2 > /tmp/conf.log 2>&1 && \
    make -j"$(nproc)" > /tmp/mk.log 2>&1 && \
    make install > /tmp/inst.log 2>&1 && \
    ls /opt/jemalloc/lib/libjemalloc.so.2

FROM ubuntu-openclaw-chromium:24.04-arm64
COPY --from=build /opt/jemalloc /opt/jemalloc
ENV LD_PRELOAD=/opt/jemalloc/lib/libjemalloc.so.2
# 构建期断言 (镜像无 python3, 用 shell): 本进程 maps 已加载 jemalloc,
# 且容器三大运行时 (supervisord=PID1 / node=openclaw+agent-browser / chromium) 均可正常启动。
RUN grep -q libjemalloc /proc/self/maps && \
    supervisord --version && \
    node -e "const a=[]; for (let i=0;i<1e5;i++) a.push(Buffer.alloc(64)); console.log('node OK under jemalloc')" && \
    chromium --version && \
    echo "jemalloc ACTIVE: $(grep libjemalloc /proc/self/maps | head -1)"
