# CerebrAMO

Router multi-IA de DesarrollAMO. La tarea pertenece a CerebrAMO, no al proveedor: si un modelo falla por cuota, autenticación o disponibilidad, CerebrAMO puede continuar con el siguiente proveedor.

## Estado

**v0.1.0** — primer núcleo ejecutable.

Orden por defecto:

1. Anthropic / Claude
2. MiniMax
3. OpenRouter

CerebrAMO usa **OpenCode como capa de proveedores**. No lee ni copia `~/.local/share/opencode/auth.json`; las credenciales las administra OpenCode.

## Claude

Para conectar Claude:

```bash
python3 cerebramo.py auth claude
```

CerebrAMO ejecuta el flujo oficial de OpenCode:

```bash
opencode auth login --provider anthropic
```

Ahí OpenCode te ofrece los métodos de autenticación disponibles para Anthropic. Si tenés una API key, podés ingresarla. Si OpenCode ofrece OAuth para tu cuenta, el login se completa en el navegador.

Después:

```bash
python3 cerebramo.py status
```

Y para probar una tarea solo con Claude:

```bash
python3 cerebramo.py run --provider claude "Respondé solamente: CEREBRAMO_OK"
```

> Una cuenta gratuita de Claude.ai y una clave de Claude API no son lo mismo. Que puedas iniciar sesión en Claude Free no garantiza que tengas cuota API ni que un cliente de terceros pueda usar ese plan. CerebrAMO no intenta reutilizar cookies, contraseñas ni tokens privados de claude.ai.

## Failover

Configurar el orden:

```bash
python3 cerebramo.py set-order claude minimax openrouter
```

Ejecutar:

```bash
python3 cerebramo.py run "Revisá este proyecto y ejecutá sus tests"
```

Si el comando de OpenCode para Claude devuelve error, CerebrAMO intenta el siguiente proveedor configurado.

Para fijar un modelo concreto:

```bash
python3 cerebramo.py set-model claude anthropic/ID_DEL_MODELO
```

Los IDs reales disponibles se pueden ver con:

```bash
opencode models anthropic
opencode models minimax
opencode models openrouter
```

## Seguridad de credenciales

- No guardar claves en Git.
- No pegar claves en `config.json`.
- CerebrAMO delega secretos a `opencode auth login`.
- `~/.config/cerebramo/config.json` guarda solo orden y nombres de modelos, con permisos `0600`.
- No se leen ni exportan credenciales de OpenCode.

## Requisitos

- Python 3.10+
- OpenCode en `PATH`

## Tests

```bash
python3 -m unittest discover -s tests -v
```
