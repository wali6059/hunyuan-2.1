# Hunyuan 3D is licensed under the TENCENT HUNYUAN NON-COMMERCIAL LICENSE AGREEMENT
# except for the third-party components listed below.
# Hunyuan 3D does not impose any additional limitations beyond what is outlined
# in the repsective licenses of these third-party components.
# Users must comply with all terms and conditions of original licenses of these third-party
# components and must ensure that the usage of the third party components adheres to
# all relevant laws and regulations.

# For avoidance of doubts, Hunyuan 3D means the large language models and
# their software and algorithms, including trained model weights, parameters (including
# optimizer states), machine-learning model code, inference-enabling code, training-enabling code,
# fine-tuning enabling code and other elements of the foregoing made publicly available
# by Tencent in accordance with TENCENT HUNYUAN COMMUNITY LICENSE AGREEMENT.

from setuptools import setup, find_packages
import torch
from torch.utils.cpp_extension import BuildExtension, CppExtension
from pybind11.setup_helpers import Pybind11Extension, build_ext
from pybind11 import get_cmake_dir
import pybind11

# build differentiable renderer
differentiable_renderer_module = CppExtension(
    "mesh_inpaint_processor",
    [
        "mesh_inpaint_processor.cpp",
    ],
    include_dirs=[pybind11.get_include()],
)

setup(
    packages=find_packages(),
    version="0.1.0",
    name="differentiable_renderer_21",
    include_package_data=True,
    package_dir={"": "."},
    ext_modules=[
        differentiable_renderer_module,
    ],
    cmdclass={"build_ext": BuildExtension},
)