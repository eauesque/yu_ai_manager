# Modelo de seguridad de extensiones

Este software tiene como característica que "cualquiera puede usar IA para crear extensiones".
Al mismo tiempo, tiene incorporado un mecanismo para proteger tu sistema de extensiones maliciosas.

Esta página explica ese mecanismo.
Está escrita para que sea comprensible incluso para personas que no son técnicas.

---

## Concepto básico

Las extensiones funcionan dentro de un **mundo protegido**.

Dentro de este mundo protegido, las extensiones pueden comportarse con relativa libertad.
Pueden agregar páginas, mostrar datos, procesar imágenes — eso es el trabajo de las extensiones.

Sin embargo, lo que está **fuera** del mundo protegido — el núcleo del sistema (core), otras extensiones, todos los archivos de tu PC — está fuera de su alcance.
Esto no es porque "esté prohibido por las reglas", sino que la estructura hace que **físicamente no puedan alcanzarlo**.

---

## Cómo funcionan los permisos

Las extensiones necesitan **permisos** para hacer algo.

Los permisos están diseñados con el mismo modelo que los permisos de aplicaciones de smartphones.

- Es natural que una aplicación de cámara solicite acceso a la cámara
- Es inusual que una aplicación de cámara solicite acceso a los contactos

Las extensiones son iguales. Si una extensión que añade marcas de agua a imágenes solicita acceso a la red, eso es algo que deberías cuestionar.

### Flujo de aprobación

1. Instalar la extensión (o pedirle a la IA que la cree)
2. YU AI Manager escanea automáticamente el código e inspecciona lo que intenta hacer
3. Se muestra una lista de los permisos que la extensión está solicitando
4. **La extensión no funcionará hasta que tú la apruebes**

Lee detenidamente la información que aparece en la pantalla de aprobación.
Presta especial atención a los permisos que se muestran en rojo.

### Después de aprobar los permisos

La extensión funciona dentro del alcance de los permisos aprobados.
Los permisos no aprobados son inaccesibles sin importar cuánto lo intente la extensión.
No es que "intente usarlos y se le deniegue", sino que "directamente no los puede ver".

---

## Tres monitoreos independientes

Tu extensión está vigilada por tres mecanismos independientes.
Los tres son independientes entre sí, y si uno es engañado, los otros dos siguen funcionando.

### 1. Escaneo de código

Analiza automáticamente el código de la extensión y detecta patrones peligrosos.
La ejecución de programas externos, las operaciones directas con la base de datos, la ejecución dinámica de código — estos se detectan instantáneamente.

### 2. Control de permisos

Cuando una extensión llama a una API, verifica si tiene un "permiso" válido.
Los permisos solo se emiten cuando tú apruebas los permisos.
Las extensiones no pueden falsificar los permisos por sí mismas.

### 3. Registro de auditoría

Todas las operaciones de la extensión están registradas.
Este registro se guarda en un lugar independiente que no puede ser modificado por la propia extensión.

Si se detecta una anomalía — por ejemplo, si intenta realizar una operación que no había declarado — se envía automáticamente una notificación y, si es necesario, se invalida el permiso de la extensión.

---

## Cuando se crea una extensión con IA

Cuando se crea una extensión desde Claude Desktop, la extensión creada se registra automáticamente en el **nivel con las restricciones más estrictas**.

Esto es lo mismo que no darle las llaves de la caja fuerte a un empleado recién contratado desde el principio.
Primero se hace funcionar con permisos limitados y, después de confirmar que no hay problemas, se agregan permisos adicionales según sea necesario.

### Qué puede hacer una extensión creada por IA

**Usable sin aprobación:**
- Mostrar datos leídos
- Agregar páginas a la interfaz de usuario
- Agregar pantallas de configuración

**Requiere aprobación:**
- Comunicación con servicios externos
- Escritura en la base de datos
- Lectura de archivos

**Imposible sin importar qué:**
- Leer o modificar el núcleo del sistema (core)
- Leer o modificar otras extensiones
- Ejecutar programas externos
- Falsificar permisos

---

## Inspecciones periódicas

Una extensión no termina de revisarse una vez aprobada.

Si el código cambia y la cantidad de cambios supera un cierto umbral, se solicitará **re-aprobación**.
Esto es para prevenir el truco de hacer cambios gradualmente hasta convertirse en algo completamente diferente sin que te des cuenta.

Además, la reinspección del código se ejecuta automáticamente de forma periódica.
Aunque no hubiera problemas en el momento de la aprobación, pueden encontrarse problemas con nuevas reglas de inspección.

---

## Lo que debes hacer

1. **Lee bien la pantalla de aprobación de permisos** — Entiende lo que se está solicitando antes de aprobar
2. **Rechaza las solicitudes de permisos inusuales** — No tiene sentido que el procesamiento de imágenes necesite acceso a la red
3. **No ignores las notificaciones** — Si se detecta una anomalía, verifica
4. **No instales extensiones de fuentes no confiables** — Esto es obvio

A la inversa, si haces eso, estarás seguro.
El mecanismo te protegerá en todo lo demás.
