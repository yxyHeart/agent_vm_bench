# 生产镜像: vanilla + 源码编译的 zlib-ng (zlib-compat, LD_PRELOAD 系统级替换)
# 构建上下文 = 本目录, 需放 zlib-ng-2.2.4.tar.gz 源码包 (j 机 ~/pdfbuild/)
# docker build -t ubuntu-document-bench:pdf-generic .

FROM ubuntu-document-bench:24.04-linuxarm64 AS build
RUN sed -i "s|ports.ubuntu.com/ubuntu-ports|repo.huaweicloud.com/ubuntu-ports|g" /etc/apt/sources.list.d/ubuntu.sources 2>/dev/null || true; \
    apt-get update && apt-get install -y --no-install-recommends build-essential cmake ninja-build && rm -rf /var/lib/apt/lists/*
COPY zlib-ng-2.2.4.tar.gz /src/
RUN cd /src && tar xf zlib-ng-2.2.4.tar.gz && cd zlib-ng-2.2.4 && \
    sed -i '/add_subdirectory(test)/d' CMakeLists.txt && mkdir build && cd build && \
    cmake -G Ninja -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_C_FLAGS="-O3 -mcpu=tsv110 -fPIC" -DZLIB_COMPAT=ON -DWITH_OPTIM=ON \
        -DCMAKE_INSTALL_PREFIX=/out/zlib-ng -DBUILD_TESTING=OFF \
        .. > /tmp/cm.log 2>&1 && ninja -j"$(nproc)" install > /tmp/mk.log 2>&1 && \
    find /out/zlib-ng -name "libz.so*"

FROM ubuntu-document-bench:24.04-linuxarm64
COPY --from=build /out/zlib-ng /opt/zlib-ng
ENV LD_PRELOAD=/opt/zlib-ng/lib/libz.so.1
RUN python3 - <<'PYEOF'
import zlib
with open("/proc/self/maps") as f:
    libs = sorted({l.split()[-1] for l in f if "libz.so" in l})
assert any("/opt/zlib-ng/" in l for l in libs), libs
blob = b"hello world" * 10000
assert zlib.decompress(zlib.compress(blob)) == blob
print("zlib-ng ACTIVE:", libs[0])
PYEOF
