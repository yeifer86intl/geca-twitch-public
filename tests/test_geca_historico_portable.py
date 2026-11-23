import datetime as dt
import tempfile
import unittest
from pathlib import Path
from geca_twitch.db import connect
from geca_twitch.aggregate import aggregate
from scripts.geca_state_release import pack, unpack, check_growth

class PersistenceAndRules(unittest.TestCase):
    def test_gzip_roundtrip_and_growth(self):
        with tempfile.TemporaryDirectory() as d:
            old=Path(d)/'old.sqlite3'; c=connect(old)
            c.execute("INSERT INTO runs(run_id,started_utc,status) VALUES ('r1','2026-11-20','success')")
            c.commit();c.close()
            packed=Path(d)/'state.sqlite3.gz';pack(old,packed)
            restored=Path(d)/'restored.sqlite3';unpack(packed,restored)
            a,b=check_growth(old,restored)
            self.assertEqual(a,b)
            c=connect(restored);c.execute("DELETE FROM runs");c.commit();c.close()
            with self.assertRaises(RuntimeError):check_growth(old,restored)

    def test_no_false_alert_when_only_13_days(self):
        with tempfile.TemporaryDirectory() as d:
            c=connect(Path(d)/'state.sqlite3');asof=dt.date(2026,12,9)
            for i in range(13):
                day=asof-dt.timedelta(days=14-i)
                c.execute('INSERT INTO game_snapshots VALUES (?,?,?,?,?,?,?)',
                          (f'c{i}','g1',f'{day}T23:00:00Z',700 if i<7 else 1400,2,1,'r'))
            self.assertEqual(aggregate(c,asof)['alerts'],0)
            c.close()

if __name__=='__main__':unittest.main()
