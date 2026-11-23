"""Estado central versionado en UN release; conserva actual y una copia anterior.
Nunca elimina una versión si no se comprobó descarga y checksum de la nueva.
"""
import argparse, gzip, hashlib, json, os, shutil, subprocess, tempfile
from pathlib import Path

TAG='estado-geca-twitch'
PREFIX='geca-twitch-state-'

def gh(*args, json_result=False):
    proc=subprocess.run(['gh',*map(str,args)],text=True,capture_output=True,encoding='utf-8')
    if proc.returncode:raise RuntimeError('gh '+' '.join(map(str,args))+'\n'+proc.stderr)
    return json.loads(proc.stdout) if json_result else proc.stdout

def assets():
    repo=os.environ.get('GECA_REPO') or os.environ.get('GITHUB_REPOSITORY')
    if not repo:raise RuntimeError('Define GECA_REPO=owner/geca-central')
    data=gh('api',f'repos/{repo}/releases/tags/{TAG}',json_result=True)
    return repo,data['assets']

def pairs():
    repo,ls=assets()
    by_name={x['name']:x for x in ls}
    versions=[]
    for a in ls:
        name=a['name']
        if name.startswith(PREFIX) and name.endswith('.sqlite3.gz'):
            stem=name.removesuffix('.sqlite3.gz')
            check=stem+'.sha256'
            if check in by_name:
                versions.append((stem,a,by_name[check]))
    return repo,sorted(versions,key=lambda x:x[0])

def digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def restore(out):
    repo,versions=pairs()
    if not versions:raise RuntimeError('No hay seed confirmada: no se crea SQLite vacía')
    stem=versions[-1][0]
    with tempfile.TemporaryDirectory() as tmp:
        name=stem+'.sqlite3.gz';check=stem+'.sha256'
        gh('release','download',TAG,'-R',repo,'-p',name,'-p',check,'-D',tmp)
        gz=Path(tmp)/name
        expected=(Path(tmp)/check).read_text().split()[0].strip()
        if digest(gz)!=expected:raise RuntimeError('SHA256 del estado remoto NO coincide')
        dest=Path(out);dest.parent.mkdir(parents=True,exist_ok=True)
        staging=dest.with_suffix('.restore.tmp')
        if staging.exists():staging.unlink()
        with gzip.open(gz,'rb') as src,open(staging,'wb') as dst:shutil.copyfileobj(src,dst)
        import sqlite3
        conn=sqlite3.connect(staging)
        try:
            if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('SQLite incorrecto')
        finally:conn.close()
        staging.replace(dest)
    print('Restaurado',stem,'a',out)

def push(source,version,bootstrap=False,prune=False):
    source=Path(source)
    if not source.is_file():raise FileNotFoundError(source)
    repo=os.environ.get('GECA_REPO') or os.environ.get('GITHUB_REPOSITORY')
    if not repo:raise RuntimeError('GECA_REPO requerido')
    try:
        _,v=pairs()
    except RuntimeError:
        if not bootstrap:raise
        gh('release','create',TAG,'-R',repo,'--title','GECA estado consolidado',
           '--notes','SQLite comprimido: estado actual y respaldo anterior.','--latest=false')
        v=[]
    stem=PREFIX+str(version).zfill(12)
    if any(s==stem for s,_,_ in v):raise RuntimeError('Versión ya existe; se prohíbe sobreescribir')
    with tempfile.TemporaryDirectory() as tmp:
        gz=Path(tmp)/(stem+'.sqlite3.gz')
        sha=Path(tmp)/(stem+'.sha256')
        if source.suffix=='.gz':
            import sqlite3
            with tempfile.TemporaryDirectory() as verify_seed:
                raw=Path(verify_seed)/'seed.sqlite3'
                with gzip.open(source,'rb') as inp,open(raw,'wb') as out:shutil.copyfileobj(inp,out)
                db=sqlite3.connect(raw)
                try:
                    if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                        raise RuntimeError('Semilla GZIP contiene SQLite corrupto')
                    if db.execute("SELECT count(*) FROM sqlite_master WHERE name='game_snapshots'").fetchone()[0]!=1:
                        raise RuntimeError('Semilla sin historial game_snapshots')
                finally:db.close()
            shutil.copyfile(source,gz)
        else:
            import sqlite3
            db=sqlite3.connect(source)
            try:
                if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('SQLite corrupto')
            finally:db.close()
            with open(source,'rb') as inp,gzip.open(gz,'wb',compresslevel=6) as out:shutil.copyfileobj(inp,out)
        sha.write_text(digest(gz)+'  '+gz.name+'\n',encoding='ascii')
        # El nuevo estado no se considera recuperable hasta tener AMBOS assets.
        gh('release','upload',TAG,str(gz),str(sha),'-R',repo)
        with tempfile.TemporaryDirectory() as verify:
            gh('release','download',TAG,'-R',repo,'-p',gz.name,'-p',sha.name,'-D',verify)
            if digest(Path(verify)/gz.name)!=(Path(verify)/sha.name).read_text().split()[0]:
                raise RuntimeError('Fallo de verificación remota: NO borrar históricos')
    print('Estado publicado y verificado:',stem)
    if prune:
        repo,valid=pairs()
        # Conservar actual + respaldo anterior. No borrar jamás el resto en caso de falla.
        for old,asset,checksum in valid[:-2]:
            for obj in (asset,checksum):gh('api','-X','DELETE',f'repos/{repo}/releases/assets/{obj["id"]}')
            print('Descartado respaldo antiguo:',old)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['restore','bootstrap','publish'])
    p.add_argument('--db',default='state/geca.sqlite3');p.add_argument('--seed-file')
    p.add_argument('--version',default=os.environ.get('GITHUB_RUN_ID','local'));p.add_argument('--prune',action='store_true')
    p.add_argument('--previous',help='compatibilidad; se valida integridad y se conserva respaldo anterior')
    a=p.parse_args()
    if a.action=='restore':restore(a.db)
    elif a.action=='bootstrap':
        if not a.seed_file:p.error('--seed-file')
        push(a.seed_file,'000000000000',bootstrap=True,prune=False)
    else:push(a.db,a.version,prune=a.prune)
