# SVE compare256 (已关闭, 真实 E2E 零收益)

手写 SVE 版 compare256 (256-bit 比对 + brkb/cntp 首差异定位), 20 万随机用例与 NEON
交叉验证一致后, 以 pragma target + HWCAP 运行时探测集成进 zlib-ng。
孤立微基准 1.8x, 真实基准 11.12 vs 11.00s 零收益 (函数在整流程占比小 + 本机
SVE 疑 2×128 拆分执行)。Dockerfile.zng-sve 构建 zng-base/zng-sve 双对照库,
probe 计量镜像的 VARIANT=base/sve 依赖它。待真 256-bit 硬件 (Neoverse V2 类) 可重估。
