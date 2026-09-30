from concurrent.futures import ThreadPoolExecutor
from PySide6.QtCore import QObject, Signal

class Coordinator(QObject):
    """All service, scan, settings and integration calls share one worker."""
    delivered = Signal(object, object, object)
    busy = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='filehub-files')
        self.pending = 0
        self.delivered.connect(self._finish)

    def submit(self, action, callback, error=None, *, lifecycle=False):
        owner=self.parent()
        binding=None
        if not lifecycle and hasattr(owner,'capture_work_authority'):
            binding=owner.capture_work_authority()
            if binding is None:
                if error:error('正在切换状态或退出；未接受新的操作。')
                return
        self.pending += 1; self.busy.emit(True)
        def run():
            try:
                if binding is not None:owner.assert_work_authority(binding)
                result, failure = action(), None
            except Exception as exc: result, failure = None, exc
            self.delivered.emit((callback, error), result, failure)
        self.executor.submit(run)

    def _finish(self, handlers, result, failure):
        self.pending -= 1
        callback, error = handlers
        if failure is None: callback(result)
        elif error: error(str(failure))
        self.busy.emit(bool(self.pending))

    def begin_wait(self):
        """Account for asynchronous settlement without occupying/joining a worker."""
        self.pending += 1; self.busy.emit(True)

    def end_wait(self):
        self.pending -= 1; self.busy.emit(bool(self.pending))

    def close(self):
        self.executor.shutdown(wait=True)
