FROM ubuntu-document-bench:24.04-linuxarm64
COPY openpyxl_cache.py oxlcache.pth /usr/local/lib/python3.12/dist-packages/
COPY lxml-6.1.2-cp312-cp312-manylinux_2_26_aarch64.manylinux_2_28_aarch64.whl /tmp/
RUN pip3 install --no-cache-dir --break-system-packages /tmp/lxml-6.1.2-cp312-cp312-manylinux_2_26_aarch64.manylinux_2_28_aarch64.whl && rm -f /tmp/lxml-*.whl
