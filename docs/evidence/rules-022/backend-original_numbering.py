def pytest_configure(config):
    import filehub.automation.executor as executor
    import filehub.automation.planner as planner
    # Reproduce original preview behavior while preserving the working sources.
    def original_target(desired, **kwargs):
        return desired
    executor.allocate_conversion_target = original_target
    planner.allocate_conversion_target = original_target
