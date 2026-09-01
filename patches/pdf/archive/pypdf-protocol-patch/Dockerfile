# pypdf 协议补丁镜像层: vanilla + runtime-setup.sh
# docker build -t ubuntu-document-bench:pdf-patched .
FROM ubuntu-document-bench:24.04-linuxarm64
COPY runtime-setup.sh /runtime-setup.sh
RUN chmod +x /runtime-setup.sh && /runtime-setup.sh
