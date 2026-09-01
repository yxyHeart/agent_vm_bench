# pypdf 运行时协议继承移除 (已归档, 单独 E2E -0.22s)

根因: pypdf 6.10 的 PdfObject(_base.py:64) 与 XmpInformation(xmp.py:193) 出于类型标注
继承了 typing.Protocol, 使所有 isinstance 走 _ProtocolMeta 慢速路径 (62,676 次/clone, 占 11%)。
Protocol 是结构化类型, 具体类无需继承。

- Dockerfile: vanilla + 补丁的镜像层
- runtime-setup.sh: 2 处 sed + 断言 (metaclass=type, 读真实模板回归)
- check_patch.py: 独立验证脚本

实测: 单次 clone 186.4→159.5ms (-14.4%), 冻结业务脚本输出 md5 逐字节一致;
与 zlib-ng 叠加 E2E 11.98→10.96s。
归档原因: 效果依赖打补丁时机与镜像分层管理, 维护成本高于收益, 不再作为独立优化点维护;
补丁本身正确且具备回馈 upstream (pypdf) 的条件, 如需启用直接复用本目录。
