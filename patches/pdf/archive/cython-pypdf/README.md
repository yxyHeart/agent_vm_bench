# pypdf Cython 编译 (已关闭)

cython_build.py 曾用于全包 (54 模块) 与叶模块 (_utils/errors) 两种编译。
全包: .so 激活但读真实模板报 "Trailer cannot be read" (元类/布局语义偏移);
叶模块: 217 vs 209ms 无收益 (热点本在 C 层)。结论: 整包自动编译不可行,
后续 native 化走窄接口 C 扩展 + 完整回退 (roadmap Phase B/C)。
