# workload-aware 层(最终版 v4, 已放弃, 留档)

> 状态: **已放弃, 勿部署。** 本层依赖对工作簿结构的感知(识别"大而简单的表"改变解析/物化/写出行为),
> 对新流程存在行为影响, 经评估不符合"零 workload 感知"约束。留档因其曾验证过该路线的收益上限:
> 单独叠加四轮达 **259s → 57.6s (-77.7%)**, Success 100%, 逐格 md5 与 stock 一致。
> 完整数据与结论见 `docs/xlsx-optimization-report.md`; 可继承部分(磁盘缓存、GC 守卫、直填槽位)
> 已剥离进 `active/`。

## 本目录内容(v4 末态)

| 文件 | 说明 |
|------|------|
| `openpyxl_cache.py` | v4 最终实现: 磁盘缓存 + 解析期 GC off + Cell 直填槽位 + 大表懒物化(字节体检/按行物化/有界窗口/流式全表遍历) + 存盘原始字节直通 |
| `oxlcache.pth` | 注入钩子 |
| `Dockerfile` | 镜像层(基础镜像 + 上述两文件; 构建目录需另备 lxml wheel, 见下) |

## 机制概要(v4 = v1..v4 累积)

1. **磁盘缓存**(v1, → active/disk-cache): 内容指纹键, MISS 落盘"壳+格表", HIT 快照重建
2. **解释器层**(v2, GC/直填已被 active/speedups 以 C 形式继承): 解析期 GC off; Cell.__new__ 直填槽位
3. **大表懒物化**(v3, 本层核心, 已放弃): 字节级体检判定"简单稠密表"后只解析头尾, 元数据即时答, 触碰才物化; 存盘直通原始压缩字节
4. **按需物化**(v4, 已放弃): 单行按需物化/有界窗口物化/全表流式遍历

环境开关(当时用于归因): `OPENPYXL_CACHE` / `OPENPYXL_LAZYRAW` / `OPENPYXL_PASSTHROUGH` /
`OPENPYXL_CACHE_FASTBIND` / `OPENPYXL_CACHE_GC` / `OPENPYXL_CACHE_DEBUG`。

## 复现(如需考古)

```bash
# 构建目录放置 lxml-6.1.2-cp312-cp312-manylinux_2_26_aarch64.manylinux_2_28_aarch64.whl 后:
docker build -t ubuntu-document-bench:xlsx-v4 <本目录>
bench-core --provider docker --config config/common/document-xlsx-v4.yaml -n 1   # ~57.6s
```
