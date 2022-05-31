@echo off
rd /s /q dist
rd /s /q build
rd /s /q mojadata.egg-info
python -m pip install --upgrade setuptools wheel
python setup.py sdist bdist_wheel
