import datetime as dt
import tempfile
import unittest
from pathlib import Path
from geca_twitch.db import connect
from geca_twitch.aggregate import aggregate


class DailyCoverageTests(unittest.TestCase):
    def create_history(self, c, asof, hour=23, day_missing=None):
        for i in range(14):
            if i == day_missing:
                continue
            day=asof-dt.timedelta(days=14-i)
            c.execute('INSERT INTO game_snapshots VALUES (?,?,?,?,?,?,?)',
                (f'c{i}', 'g1',f'{day}T{hour:02d}:17:00Z', 700 if i<7 else 1300,2,1,'r'))

    def test_14_daily_captures_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            c=connect(Path(folder)/'db.sqlite3')
            self.create_history(c,dt.date(2026,11,16))
            result=aggregate(c,dt.date(2026,11,16))
            self.assertEqual(result['alerts'],1)
            self.assertEqual(result['games_evaluable'],1)
            c.close()

    def test_midnight_utc_delay_is_same_session(self):
        with tempfile.TemporaryDirectory() as folder:
            c=connect(Path(folder)/'db.sqlite3')
            asof=dt.date(2026,11,16)
            for i in range(14):
                # 00:10 UTC del dia siguiente sigue siendo 19:00 Venezuela anterior
                target=asof-dt.timedelta(days=14-i)
                captured=target+dt.timedelta(days=1)
                c.execute('INSERT INTO game_snapshots VALUES (?,?,?,?,?,?,?)',
                    (f'c{i}','g1',f'{captured.isoformat()}T00:10:00Z',
                     700 if i<7 else 1300,2,1,'r'))
            self.assertEqual(aggregate(c,asof)['alerts'],1)
            c.close()

    def test_missing_day_is_not_alert(self):
        with tempfile.TemporaryDirectory() as folder:
            c=connect(Path(folder)/'db.sqlite3')
            self.create_history(c,dt.date(2026,11,16),day_missing=5)
            self.assertEqual(aggregate(c,dt.date(2026,11,16))['alerts'],0)
            c.close()

    def test_old_1217_hour_is_not_alert(self):
        with tempfile.TemporaryDirectory() as folder:
            c=connect(Path(folder)/'db.sqlite3')
            self.create_history(c,dt.date(2026,11,16),hour=12)
            self.assertEqual(aggregate(c,dt.date(2026,11,16))['alerts'],0)
            c.close()

    def test_wrong_hour_is_not_alert(self):
        with tempfile.TemporaryDirectory() as folder:
            c=connect(Path(folder)/'db.sqlite3')
            self.create_history(c,dt.date(2026,11,16),hour=18)
            self.assertEqual(aggregate(c,dt.date(2026,11,16))['alerts'],0)
            c.close()

if __name__=='__main__':unittest.main()
