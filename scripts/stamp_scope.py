"""Registra alcance declarado por el operador; no infiere cobertura retrospectiva.
Ambas bases reciben la misma tabla para que el exportador pueda comparar esquemas.
"""
import argparse
import sqlite3
from datetime import datetime,timezone

DDL='CREATE TABLE IF NOT EXISTS geca_capture_scope(capture_id TEXT PRIMARY KEY, scope_id TEXT NOT NULL, documented_utc TEXT NOT NULL)'
def stamp(before,after,scope):
    with sqlite3.connect(before) as prev,sqlite3.connect(after) as current:
        prev.execute(DDL)
        current.execute(DDL)
        prev.commit()
        if scope:
            if len(scope)>128 or any(c.isspace() for c in scope):raise ValueError('scope debe ser identificador sin espacios, máximo 128 caracteres')
            current.execute('ATTACH DATABASE ? AS old',(before,))
            ids=current.execute('''SELECT DISTINCT n.capture_id FROM main.game_snapshots n
                WHERE NOT EXISTS(SELECT 1 FROM old.game_snapshots o WHERE o.capture_id=n.capture_id)''').fetchall()
            timestamp=datetime.now(timezone.utc).isoformat()
            for (capture_id,) in ids:
                current.execute('INSERT OR IGNORE INTO geca_capture_scope VALUES (?,?,?)',(capture_id,scope,timestamp))
            print('Capturas documentadas:',len(ids),'alcance:',scope)
        else:
            print('AVISO: GECA_TWITCH_SCOPE_ID vacío: capturas sin alcance comprobable; no podrán activar alertas oficiales')
        current.commit()
if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--before',required=True);p.add_argument('--after',required=True);p.add_argument('--scope',default='')
    a=p.parse_args();stamp(a.before,a.after,a.scope)
