# CerebrAMO

CerebrAMO es el cerebro de recursos y proveedores de DesarrollAMO. Conserva el router multi-IA con failover, pero desde **v0.2.0** también normaliza el combustible y la salud del ecosistema: qué queda, cuánto hay, cuándo vence o resetea, de dónde viene el dato y cuándo fue comprobado.

## Estado

**v0.2.0 — Resource Dashboard core**

CerebrAMO distingue siempre entre datos observados y datos desconocidos. Si una plataforma no ofrece una API válida, no inventa saldo ni cuotas.

### Recursos locales disponibles sin API

En Linux puede leer directamente:

- RAM disponible/total;
- swap disponible/total;
- disco disponible/total;
- uptime;
- carga del host.

```bash
python3 cerebramo.py resources
```

Salida estructurada para otras piezas de DesarrollAMO:

```bash
python3 cerebramo.py resources --json
```

El JSON usa el esquema `cerebramo.resources.v1` y cada recurso incluye `id`, `name`, `category`, `state`, `available`, `maximum`, `unit`, `expires_at`, `source`, `checked_at`, `detail` y `remaining_percent` cuando puede calcularse de forma real.

## Minehost / host DAMO

El host donde vive DAMO puede aportar RAM, swap, disco, uptime y carga **desde el propio Linux**, sin depender de una API de Minehost.

Los datos comerciales del proveedor —plan, costo, próxima renovación o factura— sólo deben incorporarse desde una fuente autorizada o como dato manual explícito. Ejemplo:

```bash
python3 cerebramo.py resource-set minehost.renewal \
  --name "Minehost · renovación" \
  --category hosting \
  --available 12 \
  --maximum 30 \
  --unit days \
  --expires-at 2026-09-12 \
  --source manual:minehost
```

No se guardan contraseñas ni cookies de Minehost.

## Conectores y recursos externos

El mismo modelo sirve para cuotas de IA, GitHub, Netlify, Supabase, Resend, almacenamiento, dominios, telefonía u otros servicios. Un conector puede escribir snapshots verificados sin cambiar la estructura del tablero.

Cuando una fuente no existe o no está autorizada debe permanecer `unknown`. Por ejemplo, CerebrAMO no debe fingir una API de saldo/GB de un operador móvil si esa API no está disponible.

Estados soportados:

- `ok`
- `warning`
- `critical`
- `offline`
- `unknown`

## Router multi-IA

Orden por defecto:

1. Anthropic / Claude
2. MiniMax
3. OpenRouter

CerebrAMO usa **OpenCode como capa de proveedores**. No lee ni copia `~/.local/share/opencode/auth.json`; las credenciales las administra OpenCode.

### Autenticación

```bash
python3 cerebramo.py auth claude
python3 cerebramo.py status
```

### Failover

```bash
python3 cerebramo.py set-order claude minimax openrouter
python3 cerebramo.py run "Revisá este proyecto y ejecutá sus tests"
```

Para fijar un modelo:

```bash
python3 cerebramo.py set-model claude anthropic/ID_DEL_MODELO
```

Los IDs visibles se consultan con OpenCode:

```bash
opencode models anthropic
opencode models minimax
opencode models openrouter
```

## Seguridad

- No guardar claves en Git.
- No pegar claves en `config.json`.
- Autenticación de IA delegada a OpenCode.
- `~/.config/cerebramo/config.json` usa permisos `0600`.
- Los recursos guardan métricas y procedencia, no credenciales.
- Un valor que no puede verificarse permanece desconocido.

## Requisitos

- Python 3.10+
- OpenCode en `PATH` sólo para las funciones de IA

El tablero de recursos locales funciona aunque OpenCode no esté instalado.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

El AutoCheck además valida sintaxis Python y busca patrones obvios de secretos antes de integrar cambios.
