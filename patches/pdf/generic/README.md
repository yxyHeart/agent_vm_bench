# PDF 通用底层优化 — 构建配方与工具

通用轨道（零 workflow 侵入）的全部构建产物。基准镜像链:

```
ubuntu-document-bench:24.04-linuxarm64   vanilla 基准（对照零点）
        │  Dockerfile.pdfbuild           + 编译工具链
        ▼
pdf-build:base
        │  Dockerfile.native-libs        源码编译 zlib-ng(-O3 -mcpu=tsv110) 与 poppler → /out/
        ▼
pdf-build:native-libs
        │  Dockerfile.generic3           仅拷贝 /out/zlib-ng 到 /opt + pypdf 协议补丁
        ▼
ubuntu-document-bench:pdf-generic        生产镜像（benchmark 实际使用）
```

## 文件说明

| 文件 | 用途 |
|------|------|
| `Dockerfile.pdfbuild` | 构建环境（gcc/cmake/ninja + 开发库） |
| `Dockerfile.native-libs` | 编译 zlib-ng 2.2.4（zlib-compat）与 poppler 24.02.0；poppler 对照实验用（无收益已关闭） |
| `Dockerfile.generic3` | 生产镜像: /opt/zlib-ng + `ENV LD_PRELOAD` + 协议补丁断言 |
| `generic3_setup.sh` | pypdf 协议继承移除补丁（2 处 sed）+ 双断言（metaclass=type / libz 加载路径） |
| `Dockerfile.zng-sve` | SVE A/B 对照: 同参数构建 zng-base(NEON) 与 zng-sve(SVE compare256) 双库 |
| `compare256_neon.c.patched` | SVE 版 compare256 源码（pragma target + HWCAP 运行时探测 + NEON 回退） |
| `zcount.c` | zlib 调用探针库源码（LD_PRELOAD 拦截 deflate/inflate 计数+计时; pid+starttime 命名防容器 pid 复用覆盖） |
| `Dockerfile.probe-orig` / `Dockerfile.probe-zng` | 三变体计量镜像（vanilla+zlib-ng/NEON/SVE + 探针） |
| `check_probe.py` / `check_patch.py` | 构建期断言脚本 |
| `cython_build.py` | Cython 实验遗留（全包/叶模块均无收益，路线已关闭） |
| `collect-exact-bench.sh` / `collect-bench.sh` | 跑 bench 并收割探针日志的脚本 |

## 关键实验结论（详见 docs/pdf-generic-optimization-roadmap.md）

- zlib-ng: zlib 内部耗时 -58%（1,465→620ms/任务）, E2E 11.98→11.18s
- pypdf 协议补丁: clone -14.4%, E2E →10.96s
- SVE compare256: 孤立 1.8x 但真实 E2E 零收益, 不采纳
- 上游源码包（zlib-ng-2.2.4.tar.gz / poppler-24.02.0.tar.xz）在 j 机 `~/pdfbuild/`, 不入 git
