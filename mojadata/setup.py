# Always prefer setuptools over distutils
from setuptools import setup, find_packages

# To use a consistent encoding
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
long_description = ""
long_description_file = path.join(here, "readme.rst")
if path.exists(long_description_file):
    long_description = open(long_description_file, encoding="utf8").read()

setup(
    name="mojadata",
    version="4.2.6",
    description="Mojadata Tiler",
    long_description=long_description,
    url="https://github.com/SLEEK-TOOLS/moja.data",
    author="Moja.global",
    author_email="",
    license="MPL2",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Build Tools",
        "License :: OSI Approved :: Mozilla Public License 2.0",
        "Programming Language :: Python :: 3",
    ],
    keywords="moja.global",
    packages=find_packages(exclude=["contrib", "docs", "tests"]),
    install_requires=[
        "gdal==3.4.3", "gdal-utils==3.4.3",
        "numpy", "simplejson", "future", "psutil", "six", "ftfy"
    ],
    extras_require={},
    package_data={},
    data_files=[],
    entry_points={},
    python_requires=">=3.7"
)
