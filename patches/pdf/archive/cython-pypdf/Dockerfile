# 复原已关闭实验的构建: pypdf Cython 编译 (叶模块版; 全包版改 cython_build.py 的 leaves)
# 历史结论: 全包 54 模块编译后读真实模板报 "Trailer cannot be read" (元类/布局语义偏移);
# 叶模块 (_utils/_errors) 编译激活但 217 vs 209ms 零收益。两路均证伪, 此 Dockerfile 仅留档复现用。
# docker build -t pdf-cython:experiment .
FROM ubuntu-document-bench:24.04-linuxarm64
RUN sed -i "s|ports.ubuntu.com/ubuntu-ports|repo.huaweicloud.com/ubuntu-ports|g" /etc/apt/sources.list.d/ubuntu.sources 2>/dev/null || true; \
    apt-get update && apt-get install -y --no-install-recommends build-essential python3-dev python3-pip && \
    pip3 install --break-system-packages -i https://repo.huaweicloud.com/repository/pypi/simple cython && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /work && cp -r /usr/local/lib/python3.12/dist-packages/pypdf /work/pypdf_src && \
    cd /work && rm -rf pypdf_src/__pycache__
COPY cython_build.py /work/cython_build.py
RUN python3 /work/cython_build.py && \
    mkdir -p /out/pypdf-cython && cp -r /work/pypdf_src /out/pypdf-cython/pypdf && \
    cp -r /work/pypdf_c/pypdf/* /out/pypdf-cython/pypdf/ && \
    PYTHONPATH=/out/pypdf-cython python3 -c "import pypdf._utils as u; assert u.__file__.endswith('.so'), u.__file__; from pypdf import PdfReader; r = PdfReader('/opt/document-bench/pdf/input/of306_aug2023.pdf'); print('cython-leaf OK pages=', len(r.pages))"
