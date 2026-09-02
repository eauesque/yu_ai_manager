# Guía de desarrollo

Un manual para extender, personalizar y depurar este software por tu cuenta.

---

## La idea básica

Este software fue creado por un humano que le daba instrucciones y quejas a un agente de IA.
Cada línea de código fue escrita por IA.

En otras palabras: **tú puedes hacer lo mismo.**

No necesitas ser programador. No necesitas preguntarle al autor. Todo lo que necesitas es la voluntad de pensar con claridad, explicar con precisión y repetir.

No necesitas esa cosa con texto blanco deslizándose sobre una pantalla negra.
Deja primero esa idea preconcebida y ese prejuicio.
Todo puede hacerse visualmente ahora. Qué época para vivir.

---

## Antes de empezar

### Obtener YU AI Manager

Simplemente ejecuta el instalador.
Sigue las instrucciones en pantalla. Eso es todo.

Una cosa a recordar:
En este momento no hay actualizaciones automáticas. Cuando salga una nueva versión, ejecuta el instalador de nuevo para reemplazarlo.

### Conectar MCP

Abre YU AI Manager y ve a **Configuración → Claves de API**.
Hay una sección llamada **Fragmento de conexión MCP**. Copia el JSON con un clic.

Luego abre Claude Desktop y ve a **Configuración (ícono de engranaje) → Desarrollador → Editar configuración**.
Pega el JSON que copiaste, guarda y reinicia Claude Desktop.

Eso es todo. Eso es todo lo que se necesita para conectar.

**Sobre las claves de API:** Si quieres configurar manualmente sin el fragmento, crea una clave en la misma **Configuración → Claves de API**. Las claves que empiezan con `sk_...` se muestran solo una vez al crearlas. Cópiala en el momento.

### Verifica tu entorno

1. ¿Está corriendo YU AI Manager? — Inícialo y comprueba
2. ¿Está corriendo el servidor MCP? — Comprueba en la configuración de Claude Desktop
3. ¿Tienes acceso a un agente de IA? — Claude Desktop, o algo equivalente

Eso es todo. Estás listo.

---

## Usar MCP

Si el servidor MCP está corriendo, úsalo. Punto.

YU AI Manager tiene endpoints de ayuda integrados para agentes de IA.
A través de MCP, puedes acceder directamente a la base de datos, logs, configuración y **al código fuente mismo**.
Hacer que la IA mire directamente a través de MCP es más rápido y preciso que explicar a través de la UI del navegador.

Solo dile esto al agente de IA:

```
Conéctate al servidor MCP de YU AI Manager.
Revisa los endpoints de ayuda y dime qué puedes hacer.
```

### Dejar que MCP lea el código fuente

YU AI Manager tiene herramientas de referencia de código fuente integradas.

- **source_tree** — Muestra la estructura de archivos como un árbol
- **source_read** — Lee el contenido de un archivo especificado
- **source_search** — Búsqueda de texto completo en todo el código fuente

Los agentes de IA pueden usar estas para leer el código fuente directamente en el chat.
No es necesario abrir una carpeta en GitHub Desktop y pasársela a Claude Code.

Cuando quieras que la IA mire el código fuente, di esto:

```
Revisa la estructura de archivos con source_tree,
luego lee los archivos relevantes con source_read.
```

---

## Agregar funciones

No le pidas al autor que agregue funciones al core. La respuesta es no.

Usa el sistema de extensiones.
**Todo el trabajo puede hacerse completamente en el chat de Claude Desktop.** No necesitas levantarte de tu escritorio.

### Paso 1: Decidir qué construir en el chat

No digas solo "constrúyelo" de la nada.

Primero organiza lo que quieres en el chat de Claude Desktop.
"Quiero este tipo de función", "Quiero automatizar este tipo de operación" — verbalízalo a través de conversación con la IA.

Una vez que tengas claro qué construir, di esto:

```
Crea un documento de especificación.
```

La IA creará la especificación.

### Paso 2: Dejar que lo construya

No necesitas moverte a un banco de trabajo. Continúa en el mismo chat:

```
La especificación está lista. Impleméntala como una Extensión.
Crea el andamio con create_extension, escribe el código con write_extension_file.
Verifica que no haya problemas con validate_extension.
```

La IA creará y editará archivos de Extensión directamente a través de MCP.
En tu escritorio, todo se hace solo a través del chat.

**Pero si seguir adelante es tu decisión.**

Toma las sugerencias de la IA como referencia. Pero no estás obligado a seguirlas.
Tú eres el que tiene el propósito, no la IA.
No delegues tu juicio.

Cuando estés de acuerdo, deja que lo implemente. Si algo parece mal, dilo. Repite hasta que funcione.

Cuando la Extensión esté completa, reinicia YU AI Manager.
Aparecerá una nueva Extensión en Configuración → Extensiones. Revisa los permisos, apruébala y corre.

### Paso 3: Compartir (Opcional)

Si construiste algo útil, puedes compartirlo.
Si otros lo usan es su decisión. Nosotros hicimos, tú decides.

---

## Reportar errores

### Paso 1: Obtener los logs

Abre YU AI Manager y ve a **Configuración → Logs**.
Copia los logs alrededor del momento en que ocurrió el problema.

Si no puedes encontrar los logs, describe lo siguiente con precisión:
- Qué hiciste
- Qué esperabas que pasara
- Qué pasó en realidad

"Algo está mal" no es una descripción.

### Paso 2: Tomar una captura de pantalla o video

Si el problema es visual y las palabras no pueden describirlo:

- **Captura de pantalla**: `Windows + Shift + S`
- **Grabación de pantalla**: `Windows + Shift + R`

En Mac: Captura es `Cmd + Shift + 4`, grabación es `Cmd + Shift + 5`

Puedes arrastrar imágenes directamente al chat.
Una imagen vale mucho más que mil palabras de explicación confusa.

**También puedes compartir lo que está pasando dentro del navegador.**

Presiona `F12` en el navegador. Un panel se abrirá en el borde de la pantalla.
No necesitas entenderlo ahora mismo. Solo recuerda esto.

Cuando el agente de IA diga "abre F12 y busca errores", aquí es donde.
Si ves elementos rojos y amarillos, selecciónalos todos, cópialos y dáselos al agente tal como están.
Eso es todo lo que necesitas hacer.

### Paso 3: Publicarlo en GitHub

Publica los logs y capturas de pantalla en un issue de GitHub.
El autor podría verlo. Eventualmente. Sin garantías.

Si quieres que se arregle ahora, pasa a la siguiente sección.

---

## Arreglar errores tú mismo (Recomendado)

Más rápido que esperar al autor. De verdad.

### Herramientas

**Chat de Claude Desktop + MCP.** Eso es todo.

Pensar, investigar, arreglar — todo hecho aquí.
Puedes leer y escribir archivos de Extensión a través de MCP, y también ejecutar escaneos de código.
Nada más necesario.

### Flujo de depuración

Describe el problema en el chat de Claude Desktop.
Logs, capturas de pantalla, qué estabas haciendo, qué esperabas — ponlo todo.

Con MCP, la IA puede leer el código fuente directamente y verificar el estado del sistema. Dile:

```
Cuando hago clic en [X] en YU AI Manager, ocurre [Y]. Debería ser [Z].
Revisa los logs del backend y el estado a través de MCP.
También lee el código fuente relacionado con source_tree y source_read.
Identifica la causa y arréglala.
```

La IA identificará la causa y propondrá una solución.
Aplica la solución con write_extension_file y verifica con validate_extension.
Reinicia YU AI Manager y verifica el comportamiento.

### Qué darle al agente de IA

1. **Logs de error** — El texto sin procesar, no parafraseado
2. **Capturas de pantalla o video** — Para errores visuales
3. **Qué estabas haciendo** — La operación cuando ocurrió el problema
4. **Qué esperabas** — Qué debería haber pasado
5. **Propósito** — No solo el síntoma, sino por qué lo necesitas

### Cuando la IA no entiende

La IA no es humana. No siempre llenará los vacíos que dejaste.

- Puede hacer preguntas — responde con precisión
- Puede no funcionar como se esperaba — dile exactamente qué es diferente
- Si sigue dando respuestas fuera de tema, reformula tu solicitud
- Si te das cuenta de que falta información, agrégala
- Si las palabras no llegan, pasa los archivos relevantes

Este es trabajo iterativo. Funciona. Sigue adelante.

Es esencialmente lo mismo que dar instrucciones a un humano. Excepto que no hay ego, ni estado de ánimo, ni sentimientos de los que preocuparse — así que es mucho más simple.

---

## Limpiar lo visible primero

Antes de aplastar errores invisibles, ordena lo que puedes ver.
Rociar insecticida sobre un campo cubierto de malezas no tiene sentido. Nivela el terreno primero.

Implementaste algo. Parece que funciona. Pero si la superficie realmente está funcionando correctamente — a menudo no puedes saberlo haciendo clic tú mismo. Pierdes cosas. Dejas de notar una vez que te acostumbras.

Usa Playwright. El agente de IA operará el navegador e inspeccionará la UI de esquina a esquina.

Dile al agente de IA:

```
Usa Playwright para operar YU AI Manager y encontrar errores de UI/UX,
luego evalúa y sugiere mejoras desde una perspectiva de UX.
```

La IA operará el navegador, detectando diseños rotos, botones muertos, flujos no naturales, navegación confusa — y los reportará. No solo correcciones de errores, sino también sugerencias desde la perspectiva de "esto es difícil de usar" vendrán también.

Si aceptarlas es tu decisión, pero escúchalas todas primero.

Una vez hecho esto, pasa a las cosas invisibles.

---

## Eliminar cada error invisible

Los errores visibles pueden corregirse. El problema son los errores invisibles.

Piensa en el espacio debajo del refrigerador. Ves una cucaracha desde el frente.
Pero mueve el refrigerador, y hay todo un mundo debajo.
El software es igual. Errores que no aparecen en los logs, errores que no pueden reproducirse, errores que nadie ha activado — definitivamente existen. Es casi imposible para un humano encontrarlos todos.

El debug MCP es el insecticida para eso.

### Cómo

Dile al agente de IA:

```
Conéctate al MCP de YU AI Manager y depura todo el código fuente.
Usa source_tree para entender la estructura de archivos, luego lee archivos con source_read.
Reporta todos los errores potenciales, problemas de consistencia y cualquier cosa que pueda causar errores.
```

La IA lee el código fuente, verifica el estado real del sistema a través de MCP y saca a la luz problemas que no se muestran en la superficie.
Cuando llegue el informe, haz que los arregle.

### Ser persistente

No te detengas en una ronda.

Cuando la IA diga "eso es todo", responde con esto:

```
¿Hay algo más?
```

Sigue repitiendo esto. La IA cava un poco más profundo cada vez.
Cuando realmente diga "nada más", puedes confiar en que realmente ha terminado.

Ser persistente no es una virtud. Pero cuando se trata de errores, la persistencia es justicia.

---

## Hacer una revisión de seguridad antes de publicar

Si pretendes publicar una Extensión, ejecuta primero una revisión de seguridad.

No es difícil. Es rápido.

Solo dile al agente de IA:

```
Haz una revisión de seguridad de esta Extensión (o código).
También revisa la configuración e información del sandbox de YU AI Manager a través de MCP.
Lee los archivos relevantes con source_read y reporta cualquier problema.
```

YU AI Manager tiene una función de escaneo de código integrada para Extensiones.
Se ejecuta automáticamente cuando se carga una Extensión. Reinicia el servidor y carga la Extensión una vez.

El escaneo detecta automáticamente:
- Módulos peligrosos (`subprocess`, `ctypes`, `importlib`)
- Operaciones directas de BD (`sqlite3` — usa SandboxedDB)
- Ejecución dinámica de código (`eval`, `exec`, `__import__`)
- Acceso a red (`requests`, `urllib`, etc.)

Los problemas críticos impedirán que la Extensión se cargue. Las advertencias permiten la carga pero se registran en los logs.
Revisa los logs y corrige todos los problemas.

Si estás publicando código que corre en el sistema de otra persona, asume esa responsabilidad.

Para detalles sobre el modelo de seguridad, lee "[Extension Security Model](docs/en/help/developer/extension-security.md)."

---

## No tocar core

Con Extensiones, estás en un mundo protegido.
Si cambias lo que está protegiendo — core y Extensiones integradas — nunca olvides que afecta todo, y **tú mismo puedes quedar atrapado en la explosión.**

Si usas la versión Tauri, o en cualquier caso, no puedes tocar core o Extensiones integradas desde Claude Desktop.
No "no deberías" — es **imposible como capacidad**.
La ruta de la API no existe. No puedes tocar lo que no puedes ver.

Si absolutamente debes tocarlo, usa la versión Python. Eso es todo.

---

## Sobre la paciencia

Los agentes de IA son poderosos, pero no son magia. Algunos problemas requieren múltiples intentos.

Cuando te sientas frustrado:
- Da un paso atrás
- Relee lo que le dijiste
- Piensa en qué información falta
- Intenta desde un ángulo diferente

Los problemas se resuelven. Lo que necesitas no es gritar, sino pensar con claridad.

---

## Palabras finales

El autor construyó este software en 18 días, diciéndole a la IA qué hacer.
Cada función, cada corrección, cada decisión de diseño nació de conversaciones.

Dicho de otra manera, lo que está escrito solo en este documento es suficiente para construir algo de esa escala.

Los fundamentos son todas cosas aburridas.
Pero son el primer paso para colocar las piedras de un dique.
Cómo apilar piedras, cómo corregir el ángulo — lo aprendes sobre la marcha.
Los problemas complejos y difíciles eventualmente también se volverán solucionables.

Sin embargo, si los fundamentos se descuidan, las cosas colapsan incluso a escala modesta.

No descartes lo que está escrito arriba.
Para hacer el suelo sólido, lo más importante es hacer que la base de tus propias habilidades sea sólida como una roca.

Las herramientas están aquí. La documentación está aquí.

**Adelante.**
