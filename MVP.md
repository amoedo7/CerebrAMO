# MVP · CerebrAMO

## Resultado que debe entregar
Un operador puede ver recursos reales disponibles y ejecutar una solicitud de IA con orden de proveedores/failover, distinguiendo siempre dato observado de dato desconocido.

## Flujo mínimo
1. Leer RAM/swap/disco/uptime/carga local.
2. Mostrar fuente y checked_at.
3. Permitir registrar recurso externo manual/verificado.
4. Mantener estado ok/warning/critical/offline/unknown.
5. Configurar orden de proveedores IA.
6. Delegar autenticación a OpenCode.
7. Ejecutar prompt.
8. Si falla un proveedor, intentar siguiente según política.
9. Registrar qué proveedor/modelo resolvió.

## Criterios obligatorios
- no leer/copiar credenciales de OpenCode;
- recursos sin fuente permanecen unknown;
- config local 0600 donde aplique;
- dashboard local funciona sin IA;
- failover no duplica side effects externos;
- salida JSON versionada.

## Fuera del MVP
- inventar cuotas/saldos;
- almacenar API keys en Git;
- seleccionar proveedor sin dejar trazabilidad.
