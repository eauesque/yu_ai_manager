# Directrices de Seguridad de API

Utilice este documento cuando agregue o cambie un endpoint de API.

## Primera decisión

Cada endpoint debe clasificarse de antemano como uno de los siguientes:

- `public`
- `session/user`
- `admin`
- `localhost-only`

Si no está seguro, elija `admin`.

## Reglas básicas

1. No asuma que `GET` es seguro.
2. Las `read-only API keys` son solo para lecturas simples.
3. Los caminos internos, inventarios, historial, contenido, registros y resultados de análisis son `admin`.
4. Las verificaciones de localhost deben usar helpers conscientes de proxy.
5. Los endpoints de configuración requieren listas de permitidos y validación estricta.
6. Los secretos deben estar cifrados y redactados a través de helpers compartidos.

## No seguro para llaves de solo lectura

- caminos internos
- inventarios de ID de archivo/miembro
- prompts, anotaciones, transcripciones, registros de chat
- resultados OCR / análisis
- cola, historial, auditoría, aprobación, programador, estado de error de escaneo
- estado de backend de extensión / perfil / respaldo / webhook / secreto
- resultados obtenidos con credenciales de terceros almacenadas

## Verificaciones de localhost

No use directamente:

```
request.remote_addr == "127.0.0.1"
```

Use helpers existentes en su lugar:

- `get_client_ip()`
- `is_local_request()`
- `is_loopback_request()`

## Reglas de endpoint de configuración

Requerido:

- lista de permitidos de claves
- validación de tipo estricta
- validación de rango / enum / URL
- redacción de secreto en lecturas
- almacenamiento cifrado para secretos

Prohibido:

- `config.update(...)` ciego
- `bool(value)` para booleanos de solicitud
- fusiones genéricas que evitan el manejo de secretos

## Secretos

- nunca devuelva valores de secreto actuales
- nunca incluya tokens/encabezados/blobs secretos en endpoints de lista
- nunca sobrescriba secretos existentes con marcadores de posición enmascarados
- siempre use un almacén dedicado o helper compartido

## Solicitudes salientes de APIs

No haga sondeos ascendentes o búsquedas de descubrimiento desde endpoints `GET`.

Si es inevitable:

- requiera `admin`
- mantenga los tiempos de espera cortos
- bloquee localhost / IP privada / objetivos de metadatos

## Pruebas mínimas

Para endpoints sensibles, agregue:

1. `read-only key -> 403`
2. `admin key -> 200`
3. `invalid input -> 400`
4. comprobaciones de redacción de secretos
5. pruebas de regresión de localhost conscientes de proxy donde sea relevante

## Lista de verificación de revisión

- ¿Es este `GET` realmente seguro para acceso público/solo lectura?
- ¿Expone caminos, inventarios, prompts, transcripciones, historial o metadatos sin procesar?
- ¿Filtra secretos?
- ¿Utiliza helpers conscientes de proxy?
- ¿Evita coerción booleana implícita?
- ¿Evita fusiones de configuración ciegas?
- ¿Evita solicitudes salientes no intencionadas?
- ¿Incluye pruebas de regresión de alcance de administrador?

Política predeterminada: comience limitado, luego abra deliberadamente solo cuando sea necesario.
