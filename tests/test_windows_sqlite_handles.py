"""Regresión: SQLite debe cerrar sus handles antes de borrar archivos en Windows."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from geca_twitch.db import connect
from scripts import geca_state_release as state


class MonitoredConnection(sqlite3.Connection):
    opened = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.closed_explicitly = False
        type(self).opened.append(self)

    def close(self):
        self.closed_explicitly = True
        return super().close()


class SqliteWindowsHandleTests(unittest.TestCase):
    def test_pack_closes_all_sqlite_connections(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / 'original.sqlite3'
            c = connect(db)
            c.execute("INSERT INTO runs (run_id, started_utc, status) VALUES ('test', '2026-11-23', 'success')")
            c.commit()
            c.close()
            MonitoredConnection.opened = []
            original_connect = sqlite3.connect

            def tracked_connect(*args, **kwargs):
                return original_connect(*args, **dict(kwargs, factory=MonitoredConnection))

            with patch.object(state.sqlite3, 'connect', side_effect=tracked_connect):
                state.pack(db, Path(folder) / 'estado.sqlite3.gz')

            self.assertGreater(len(MonitoredConnection.opened), 1)
            self.assertTrue(all(c.closed_explicitly for c in MonitoredConnection.opened))
            self.assertFalse(list(Path(folder).glob('snapshot.sqlite3')))


if __name__ == '__main__':
    unittest.main()
