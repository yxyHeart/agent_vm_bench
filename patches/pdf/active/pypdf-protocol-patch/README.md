# pypdf 运行时协议继承移除 (E2E -0.22s, 已启用)

根因: pypdf 6.10 的 PdfObject(_base.py:64) 与 XmpInformation(xmp.py:193) 出于类型标注
继承了 typing.Protocol, 使所有 isinstance 走 _ProtocolMeta 慢速路径 (62,676 次/clone, 占 11%)。
Protocol 是结构化类型, 具体类无需继承。

- Dockerfile: `FROM` 上游镜像 + 补丁层 (生产组合 = 以 zlib-ng 镜像为基, 见下)
- runtime-setup.sh: 2 处 sed + 断言 (metaclass=type, 读真实模板回归)
- check_patch.py: 独立验证脚本

实测: 单次 clone 186.4→159.5ms (-14.4%), 冻结业务脚本输出 md5 逐字节一致;
与 zlib-ng 叠加 E2E 11.18→10.96s (镜像 `ubuntu-document-bench:pdf-generic` v3, j 机已构建验证)。

## 部署

```bash
# 单独补丁层 (基于 vanilla):
docker build -t ubuntu-document-bench:pdf-patched .
# 生产组合 v3 (zlib-ng + 本补丁): 以 active/zlib-ng 构建的镜像为基执行 runtime-setup.sh,
# 即 roadmap §六 的 pdf-generic v3 (11.98→10.96s, -8.5%)
```

曾因维护成本归档, 现恢复为 active; 补丁具备回馈 upstream (pypdf) 的条件。
