# GECA Twitch público — 19:00 Venezuela

- Repositorio: `yeifer86intl/geca-twitch-public`, sube el CONTENIDO de `geca-twitch/`.
- Workflow: `.github/workflows/geca-twitch.yml`, UTC 23:00 (19:00 Venezuela).
- Steam fuente: `yeifer86intl/geca-radar-public` (variable `STEAM_REPO` en YAML). Cambia si se usa otro nombre.
- GitHub Secrets: `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET`; **no** subir `.env`.
- El workflow descarga el release `estado-geca`, comprueba que fue actualizado HOY en Venezuela, y extrae solamente la hoja `seguimiento_activo` como maestro de 3 meses. Si no hay release de hoy, falla antes de ingesta.
- La base SQLite se recupera del artifact más reciente `geca-twitch-state`, y se publica de nuevo con cada ejecución. **La retención 30 días no garantiza respaldo permanente**; guarda copias fuera de GitHub o implementa respaldo persistente antes de producción.
- Para arrancar ejecuta primero Steam manualmente (opción primer arranque), espera a que termine y publique el release, y luego ejecuta Twitch manualmente en su repositorio.
- `gh` CLI está disponible en el runner `ubuntu-latest` alojado en GitHub.
- Una sola observación diaria significa que la regla de 14 días requiere 14 días de capturas válidas; no se calculan métricas en tiempo real de toda la jornada.
