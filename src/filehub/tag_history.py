"""Reusable preview tags, isolated from the action journal.

Construction is deliberately free of filesystem I/O. Call operations from the
application's serial worker, which shares the engine's per-state process lock.
"""
from contextlib import contextmanager
from pathlib import Path
import sqlite3

from .models import checked_path
from .platform.windows import process_lock


class TagHistory:
    def __init__(self, state_dir):
        self.state_dir = Path(state_dir)
        self.path = self.state_dir / 'tag-history.sqlite'

    @contextmanager
    def connection(self):
        state = checked_path(self.state_dir)
        state.mkdir(parents=True, exist_ok=True)
        with process_lock(state).acquire():
            path = checked_path(self.path)
            db = sqlite3.connect(path)
            try:
                with db:
                    db.execute('CREATE TABLE IF NOT EXISTS tags ('
                               'sequence INTEGER PRIMARY KEY AUTOINCREMENT, '
                               'tag TEXT NOT NULL UNIQUE)')
                    yield db
            finally:
                db.close()

    @staticmethod
    def _list(db):
        return tuple(row[0] for row in db.execute('SELECT tag FROM tags ORDER BY sequence DESC'))

    def list(self):
        with self.connection() as db:
            return self._list(db)

    def remember(self, tag):
        tag = tag.strip()
        with self.connection() as db:
            if tag:
                db.execute('DELETE FROM tags WHERE tag=?', (tag,))
                db.execute('INSERT INTO tags(tag) VALUES(?)', (tag,))
            return self._list(db)

    def remove(self, tag):
        with self.connection() as db:
            db.execute('DELETE FROM tags WHERE tag=?', (tag.strip(),))
            return self._list(db)

    def clear(self):
        with self.connection() as db:
            db.execute('DELETE FROM tags')
            return self._list(db)
