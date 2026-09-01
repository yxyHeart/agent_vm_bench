import os

import Cython.Build
import Cython.Compiler.Options
from setuptools import Distribution, Extension
from setuptools.command.build_ext import build_ext

src_root = "/work/pypdf_src"
out_root = "/work/pypdf_c"
os.makedirs(out_root, exist_ok=True)

leaves = ["_utils.py", "errors.py"]
exts = []
for rel in leaves:
    exts.append(Extension("pypdf." + rel[:-3].replace("/", "."), [os.path.join(src_root, rel)]))

Cython.Compiler.Options.get_directive_defaults()["binding"] = True
Cython.Compiler.Options.docstrings = False

dist = Distribution({"ext_modules": exts, "name": "pypdf_cython"})
dist.package_dir = {"pypdf": src_root}
cmd = build_ext(dist)
cmd.build_lib = out_root
cmd.parallel = True
cmd.ensure_finalized()
cmd.run()
print("compiled:", len(exts), "modules")
