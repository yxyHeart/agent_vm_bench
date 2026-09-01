# zlib 调用计量工具

- zcount.c: 探针源码, `gcc -O2 -shared -fPIC -o libzcount.so zcount.c -ldl`
  LD_PRELOAD 拦截 deflate/inflate/adler32/crc32, 精确计数+计时, 退出落盘 /tmp/zcount/;
  日志名 pid+starttime, 防容器 pid 复用互相覆盖 (早期版本因此漏采 4 倍)。
- Dockerfile.probe: 计量镜像, ARG VARIANT 切三态:
  `VARIANT=none`(系统 zlib) / `base`(zlib-ng NEON) / `sve`(SVE compare256, 需 archive 的 zng-sve 对照库)
- collect-exact-bench.sh: create-only + detect 跑 bench, 结束后完整收割探针日志
- collect-bench-legacy.sh: 早期轮询版 (有 pid 复用漏采问题, 留档)
