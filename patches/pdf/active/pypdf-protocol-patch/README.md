# pypdf 运行时协议继承移除 (E2E -0.22s)

根因: pypdf 6.10 的 PdfObject(_base.py:64) 与 XmpInformation(xmp.py:193) 出于类型标注
继承了 typing.Protocol, 使所有 isinstance 走 _ProtocolMeta 慢速路径 (62,676 次/clone, 11%)。
Protocol 是结构化类型, 具体类无需继承。

- runtime-setup.sh: 2 处 sed + 构建期断言 (metaclass=type; 集成于 Dockerfile.runtime)
- check_patch.py: 独立验证 (读真实模板回归)

单次 clone 186.4→159.5ms (-14.4%); 冻结业务脚本输出 md5 逐字节一致。
