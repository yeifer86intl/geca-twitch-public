"""Estado durable Twitch: SQLite comprimido en GitHub Release, con control de integridad.
Usar desde GitHub Actions o GitHub CLI local. Sin dependencias Python externas.
"""
import argparse
import datetime as dt
import gzip
import hashlib
import json
import os
import pathlib
import shutil
import sqlite3
import subprocess
import tempfile

TAG='estado-geca-twitch'
ASSET='geca_twitch.sqlite3.gz'
KEY_TABLES=('game_snapshots','stream_snapshots','video_observations','clip_observations','editorial_decisions','geca_signals','runs')

def gh(*args, allow_failure=False):
    p=subprocess.run(['gh',*args],capture_output=True,text=True)
    if p.returncode and not allow_failure:
        raise RuntimeError('gh '+ ' '.join(args) + ': '+p.stderr.strip()[:800])
    return p

def metrics(path):
    uri=pathlib.Path(path).resolve().as_uri()+'?mode=ro'
    c=sqlite3.connect(uri,uri=True)
    try:
        check=c.execute('PRAGMA integrity_check').fetchone()[0]
        if check!='ok':raise RuntimeError('SQLite defectuoso: '+str(check))
        tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        counts={t:c.execute('SELECT COUNT(*) FROM "'+t+'"').fetchone()[0] for t in KEY_TABLES if t in tables}
        return counts
    finally:c.close()

def pack(source,dest):
    """Copia SQLite coherente (backup API) y compresión gzip portable."""
    source=pathlib.Path(source);dest=pathlib.Path(dest);dest.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        snapshot=pathlib.Path(temp)/'snapshot.sqlite3'
        # IMPORTANTE: sqlite3.Connection.__exit__ hace commit/rollback, pero NO
        # cierra la conexión. Windows bloquea la eliminación del snapshot hasta
        # cerrar TODOS los handles de SQLite explícitamente.
        src = sqlite3.connect(f'file:{source.resolve()}?mode=ro', uri=True)
        try:
            dst = sqlite3.connect(snapshot)
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        metrics(snapshot)
        with snapshot.open('rb') as fi,gzip.open(dest,'wb',compresslevel=6) as fo:
            shutil.copyfileobj(fi,fo,1024*1024)

def unpack(source,dest):
    source=pathlib.Path(source);dest=pathlib.Path(dest);dest.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=dest.parent,suffix='.sqlite3',delete=False) as tmp:
        staged=pathlib.Path(tmp.name)
        try:
            with gzip.open(source,'rb') as fi:shutil.copyfileobj(fi,tmp,1024*1024)
        except Exception:
            staged.unlink(missing_ok=True);raise
    try:metrics(staged);os.replace(staged,dest)
    except Exception:staged.unlink(missing_ok=True);raise

def check_growth(before,after):
    a=metrics(before);b=metrics(after)
    regressions={k:(v,b.get(k,-1)) for k,v in a.items() if b.get(k,-1)<v}
    if regressions:raise RuntimeError('Pérdida de registros: '+json.dumps(regressions))
    return a,b

def restore(args):
    dest=pathlib.Path(args.db)
    if dest.exists():raise RuntimeError('El destino ya existe; no sobrescribir datos existentes: '+str(dest))
    repo=args.repo or os.getenv('GITHUB_REPOSITORY')
    if not repo:raise RuntimeError('Falta --repo / GITHUB_REPOSITORY')
    if args.seed:
        # Solamente durante el primer arranque explícito, antes de configurar el release.
        if gh('release','view',TAG,'-R',repo,allow_failure=True).returncode==0:
            raise RuntimeError('Ya existe estado remoto; prohibido iniciar desde --seed')
        source=pathlib.Path(args.seed)
        if source.suffix=='.gz':unpack(source,dest)
        else:
            old = sqlite3.connect(f'file:{source.resolve()}?mode=ro', uri=True)
            try:
                new = sqlite3.connect(dest)
                try:
                    old.backup(new)
                finally:
                    new.close()
            finally:
                old.close()
        print('Semilla de migración restaurada:',metrics(dest))
        return
    if gh('release','view',TAG,'-R',repo,allow_failure=True).returncode!=0:
        raise RuntimeError('NO existe estado persistente. Publica primero una semilla verificada; no se crea base vacía.')
    with tempfile.TemporaryDirectory() as temp:
        gh('release','download',TAG,'-R',repo,'--pattern',ASSET,'--dir',temp)
        source=pathlib.Path(temp)/ASSET
        if not source.exists():raise RuntimeError('Release sin el asset '+ASSET)
        unpack(source,dest)
    print('Estado restaurado:',metrics(dest))

def publish(args):
    repo=args.repo or os.getenv('GITHUB_REPOSITORY')
    if not repo:raise RuntimeError('Falta --repo / GITHUB_REPOSITORY')
    path=pathlib.Path(args.db)
    if not path.is_file():raise RuntimeError('Falta DB: '+str(path))
    if args.previous:
        check_growth(args.previous,path)
    elif gh('release','view',TAG,'-R',repo,allow_failure=True).returncode==0:
        raise RuntimeError('Publicación bloqueada: falta --previous para verificar continuidad')
    counts=metrics(path)
    with tempfile.TemporaryDirectory() as temp:
        archive=pathlib.Path(temp)/ASSET
        pack(path,archive)
        # Respaldar instantánea anterior antes de sobrescribir estado.
        if args.previous and dt.datetime.now(dt.timezone.utc).weekday()==6:
            # Respaldo inmutable semanal: evita crecer 30 MB por cada día.
            old=pathlib.Path(temp)/'geca_twitch_previo.sqlite3.gz'
            pack(args.previous,old)
            run=os.getenv('GITHUB_RUN_ID') or dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d%H%M%S')
            tag='respaldo-geca-twitch-'+dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d')
            gh('release','create',tag,str(old),'-R',repo,'--title',tag,'--notes','Respaldo previo inmutable')
        if gh('release','view',TAG,'-R',repo,allow_failure=True).returncode==0:
            gh('release','upload',TAG,str(archive),'-R',repo,'--clobber')
        else:
            gh('release','create',TAG,str(archive),'-R',repo,'--title','GECA Twitch: estado persistente','--notes','SQLite comprimido acumulativo, sin credenciales')
    print('Estado publicado:',counts)

def main():
    p=argparse.ArgumentParser()
    sp=p.add_subparsers(dest='command',required=True)
    a=sp.add_parser('restore');a.add_argument('--repo');a.add_argument('--db',default='state/geca_twitch.sqlite3');a.add_argument('--seed')
    a=sp.add_parser('publish');a.add_argument('--repo');a.add_argument('--db',default='state/geca_twitch.sqlite3');a.add_argument('--previous')
    a=sp.add_parser('pack');a.add_argument('--db',required=True);a.add_argument('--out',required=True)
    a=p.parse_args()
    if a.command=='restore':restore(a)
    elif a.command=='publish':publish(a)
    else:pack(a.db,a.out);print('Base comprimida:',a.out)
if __name__=='__main__':main()
