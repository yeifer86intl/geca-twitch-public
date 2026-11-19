"""Importa únicamente seguimiento_activo de un release histórico Steam público.

Descarga estado-geca/geca_steam_historico.xlsx con gh CLI. Exige, por defecto,
publicación del asset durante el mismo día en Venezuela; si Steam falló no
vuelve a ingerir un catálogo viejo como si fuese nuevo. No toca la SQLite.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
from zoneinfo import ZoneInfo
import pandas as pd

REQUIRED = {'appid', 'nombre', 'lanzamiento', 'ficha_verificada_utc'}
KEEP = ['appid','nombre','lanzamiento','resenas_total','resenas_positivas',
        'resenas_negativas','ficha_verificada_utc','coming_soon','ficha_estado',
        'ejecucion']

def command(args, env):
    result = subprocess.run(args, env=env, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f'No pudo consultarse el release: {result.stderr[:450]}')
    return result.stdout

def run(repo, out, result_csv, require_today=True):
    token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN', '')
    if not token:
        raise RuntimeError('Falta GH_TOKEN/GITHUB_TOKEN del propio workflow')
    env = {**os.environ, 'GH_TOKEN': token}
    metadata = json.loads(command([
        'gh','api',f'repos/{repo}/releases/tags/estado-geca',
    ], env))
    assets = [x for x in metadata.get('assets', [])
              if x.get('name') == 'geca_steam_historico.xlsx']
    if len(assets) != 1:
        raise RuntimeError('Release estado-geca sin Excel único: no se reiniciará el histórico')
    modified = assets[0].get('updated_at') or assets[0].get('created_at')
    if not modified:
        raise RuntimeError('Release sin marca temporal verificable')
    when = dt.datetime.fromisoformat(modified.replace('Z','+00:00')).astimezone(ZoneInfo('America/Caracas'))
    today = dt.datetime.now(ZoneInfo('America/Caracas')).date()
    if require_today and when.date() != today:
        raise RuntimeError(f'Catálogo Steam no actualizado hoy ({today} Venezuela); último asset: {when.isoformat()}. Twitch no ejecutará una ingesta con datos antiguos')
    output = Path(out);output.parent.mkdir(parents=True,exist_ok=True)
    command(['gh','release','download','estado-geca','--repo',repo,
             '--pattern','geca_steam_historico.xlsx','--dir',str(output.parent),
             '--clobber'],env)
    source = output.parent/'geca_steam_historico.xlsx'
    if source.resolve()!=output.resolve():
        output.write_bytes(source.read_bytes())
    with pd.ExcelFile(output, engine='openpyxl') as book:
        if 'seguimiento_activo' not in book.sheet_names:
            raise ValueError('El histórico Steam carece de seguimiento_activo: no se usará vigente como sustituto')
        active=pd.read_excel(book, sheet_name='seguimiento_activo',dtype={'appid':str})
    if not REQUIRED.issubset(active.columns):
        raise ValueError(f'Columnas obligatorias ausentes: {REQUIRED - set(active.columns)}')
    if active['appid'].isna().any() or active['appid'].duplicated().any():
        raise ValueError('AppID nulos o duplicados en seguimiento_activo')
    for col in KEEP:
        if col not in active.columns: active[col] = ''
    result=Path(result_csv);result.parent.mkdir(parents=True,exist_ok=True)
    active[KEEP].to_csv(result,sep=';',index=False,encoding='utf-8-sig')
    print(f'Importados {len(active)} juegos activos de Steam (ventana de 3 meses); '+
          f'histórico completo conservado en release. Actualización: {when.isoformat()}',flush=True)
    return len(active)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--repo',required=True)
    parser.add_argument('--out',default='data/geca_steam_historico.xlsx')
    parser.add_argument('--csv',default='data/steam_maestro_actual.csv')
    parser.add_argument('--require-today',action='store_true')
    args=parser.parse_args()
    run(args.repo,args.out,args.csv,require_today=args.require_today)
