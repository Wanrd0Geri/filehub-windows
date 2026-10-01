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

    def submit(self, action, callback, error=None):
        self.pending += 1; self.busy.emit(True)
        future = self.executor.submit(action)
        def done(f):
            try: result, failure = f.result(), None
            except Exception as exc: result, failure = None, exc
            self.delivered.emit((callback, error), result, failure)
        future.add_done_callback(done)

    def _finish(self, handlers, result, failure):
        self.pending -= 1
        callback, error = handlers
        if failure is None: callback(result)
        elif error: error(str(failure))
        self.busy.emit(bool(self.pending))

    def close(self):
        self.executor.shutdown(wait=True)
