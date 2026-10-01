"""Thin freezer entry: preserve package-relative imports in __main__."""
import runpy

runpy.run_module("filehub", run_name="__main__")
