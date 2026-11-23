"""Genera cambios REALES entre SQLite antes/después; no exporta la base entera."""
import argparse, gzip, hashlib, json, sqlite3
from pathlib import Path

TABLES = ('steam_games','twitch_games','game_matches','match_candidates','runs',
          'stream_snapshots','game_snapshots','twitch_videos','video_observations',
          'twitch_clips','clip_observations','geca_capture_scope')

def export(before, after, out, repo, run_id):
    if not Path(before).is_file() or not Path(after).is_file():
        raise FileNotFoundError('Se requieren AMBAS bases previa y posterior; no se crea un delta sin estado anterior')
    db=sqlite3.connect(f'file:{Path(after).resolve().as_posix()}?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    db.execute('ATTACH DATABASE ? AS old',(str(Path(before).resolve()),))
    Path(out).parent.mkdir(parents=True,exist_ok=True)
    tmp=str(out)+'.tmp'
    total={}
    with gzip.open(tmp,'wt',encoding='utf-8',compresslevel=6) as f:
        f.write(json.dumps({'_manifest':{'source':repo,'run_id':str(run_id),'kind':'twitch'}},ensure_ascii=False)+'\n')
        for table in TABLES:
            schema=db.execute('PRAGMA main.table_info("'+table+'")').fetchall()
            keys=[r['name'] for r in sorted(schema,key=lambda z:z['pk']) if r['pk']]
            cols=[r['name'] for r in schema]
            if not keys:raise ValueError('Tabla sin clave estable: '+table)
            old_cols={r['name'] for r in db.execute('PRAGMA old.table_info("'+table+'")')}
            if set(cols)!=old_cols: # incluye cambios de esquema; evita perder cambios por columnas nuevas
                raise RuntimeError(f'Esquema no coincide en {table}; migrar base previa antes de exportar')
            joins=' AND '.join(f'a."{k}" IS b."{k}"' for k in keys)
            changed=' OR '.join(f'a."{c}" IS NOT b."{c}"' for c in cols if c not in keys)
            query=(f'SELECT a.* FROM main."{table}" a LEFT JOIN old."{table}" b ON {joins} '
                   f'WHERE b."{keys[0]}" IS NULL OR ({changed})')
            n=0
            for row in db.execute(query):
                f.write(json.dumps({'table':table,'row':dict(row)},ensure_ascii=False,separators=(',',':'))+'\n')
                n+=1
            total[table]=n
    Path(tmp).replace(out)
    db.close()
    print(json.dumps({'out':str(out),'rows':total,'bytes':Path(out).stat().st_size},ensure_ascii=False))
    return total

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--before',required=True);p.add_argument('--after',required=True)
    p.add_argument('--out',required=True);p.add_argument('--repo',required=True);p.add_argument('--run',required=True)
    a=p.parse_args();export(a.before,a.after,a.out,a.repo,a.run)
