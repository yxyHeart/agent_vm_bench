# PDF 基准优化前后火焰图对比 (系统 zlib vs zlib-ng)

## 文件清单

| 文件 | 内容 |
|------|------|
| `flame-full-before.svg` / `flame-full-after.svg` | 全景火焰图 (fill + render 全 workload, 含 Python 帧与 native 帧) |
| `png-zlib-before.svg` / `png-zlib-after.svg` | **主对比图**: 只裁剪 PNG 编码→zlib 路径 (跳过未优化的 fill/read 等路径) |
| `flame-diff.svg` | 差分火焰图 (蓝=耗时减少, 红=增加; 仅叶帧着色为 flamegraph.pl 行为) |
| `before.folded` / `after.folded` / `diff.folded` | 折叠栈原始数据 (可复算全部数字) |
| `wl.py` | 采样 workload: 复刻 P03 (10× fill[配方 18 字段] + 10× render[pdftoppm -r 200 + PIL cl=6]) × 3 轮 |
| `symize.py` / `crop.py` / `normalize.py` / `clean.py` / `fix_title.py` / `make_flames.sh` | 处理管线 (符号化/裁剪/归一化/清洗/生成) |

## 关键数字 (99Hz 采样, 样本数 ∝ Python 进程 CPU 时间)

| 指标 | 系统 zlib | zlib-ng | 变化 |
|------|----------:|--------:|-----:|
| 总样本 | 2,080 | 1,577 | **-24.2%** |
| zlib 帧样本 | 948 (45.6%) | 477 (30.2%) | **-49.7%** |
| PNG-save 路径样本 | 1,443 | 906 | -37.2% |
| render 路径样本 | 1,460 | 916 | -37.3% |
| fill 路径样本 (未优化对照) | 605 | 638 | +5.5% (噪声内, 未受影响) |

读图要点: 优化前 libz 占 Python 侧 CPU 的 45.6% (火焰图中 `_encode_tile` 下方的大块), 优化后缩到 30.2%;
fill (pypdf 读/克隆/写, 未优化) 两侧持平, 证明收益全部来自 zlib 替换。

## 采集方法

1. **py-spy 0.4.2 `record -n`(native) 99Hz**, 在容器内直接运行 (宿主机 perf 对容器进程无法解析符号, py-spy 跨容器 native 展开会 `UNW_EBADREG`)。
   需 `--cap-add SYS_PTRACE --security-opt seccomp=unconfined` (docker 默认 seccomp 禁 ptrace/personality)。
2. `setarch -R` 关闭 ASLR → libz/libc 加载基址固定 → `symize.py` 用 `readelf` dynsym 事后符号化 stock 侧裸地址帧。
   Ubuntu libz 已剥离且内部函数为静态符号, 无法命中的区间折叠为 `libz内部(符号剥离)`; zlib-ng 自编译未剥离, `deflate_medium` / `longest_match_neon` / `adler32_fold_copy_c` 等内部函数名直接可见。
3. 标题乱码: flamegraph.pl 对 `--title` 传入的 UTF-8 会双重编码 (帧名无损), `fix_title.py` 做可逆修复。
4. 差分图对齐: `normalize.py` 将两侧 libz/libc 连续帧折叠为统一帧名、只保留 Python 帧 (两侧 native 展开深度不一致会导致栈键错位), 再剥行号后 `difffolded.pl`。
5. `pdftoppm` 是子进程, 不在 Python 采样内 (未优化项, 按需跳过)。

## 已知局限

- 每轮 ~4% 采样错误 (76-80 errors / run), py-spy 暂停式采样对两变体同等影响。
- stock 侧 zlib 内部函数不可细分 (发行版剥离); 差异归因到模块级。
- 样本仅覆盖 Python 主进程, 不含 pdftoppm 的原生渲染时间 (~1.9s/轮, 两变体相同)。

## 复现 (j 机)

```bash
docker run --rm --cap-add SYS_PTRACE --security-opt seccomp=unconfined \
  -v /tmp/pyspy:/p -v $PWD/wl.py:/wl.py -v $PWD:/out \
  ubuntu-document-bench:24.04-linuxarm64 \
  /p record -n -r 99 -d 45 -f raw -o /out/b.raw -- setarch -R python3 /wl.py
# zng 侧同命令换镜像 ubuntu-document-bench:pdf-zng
bash make_flames.sh   # 清洗/符号化/裁剪/差分 -> 全部 SVG
```
