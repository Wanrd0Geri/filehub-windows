from pathlib import Path


def pytest_configure(config):
    # pytest does not create the parent of an explicit basetemp. Keep all test
    # mutations under the workspace, without deleting the larger sandbox.
    (Path(config.rootpath) / "sandbox").mkdir(exist_ok=True)
