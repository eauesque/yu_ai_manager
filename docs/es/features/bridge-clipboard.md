# Atajo del Portapapeles de Puente

En las páginas NAI Bridge / ComfyUI Bridge / SD WebUI Bridge, una tecla de acceso rápido te permite
enviar instantáneamente el texto del portapapeles al campo de prompt. Cuando has copiado un prompt
desde otra ventana, puedes aplicarlo sin antes hacer clic en el área de texto.

## Atajo

| SO | Teclas |
|---|---|
| Windows / Linux | `Ctrl` + `Alt` + `V` |
| macOS | `⌘` + `⌥` + `V` |

Esto se añade junto con el pegado nativo del navegador (`Ctrl`+`V`) y no
interfiere con el comportamiento existente de pegado.

## Comportamiento

1. Abre una de las páginas de Bridge
2. Copia texto de una fuente externa (`Ctrl`+`C`)
3. Presiona `Ctrl`+`Alt`+`V` mientras la página de Bridge tiene enfoque
4. Selección de destino:
   - Si un área de texto está enfocada → se inserta en la posición del cursor en ese área de texto
   - Si nada está enfocado → se inserta en el campo de prompt positivo (NAI: `#nabPrompt` / ComfyUI: `#cfbPrompt` / SD: `#sdwbPrompt`)
5. En caso de éxito, se muestra un toast "Clipboard text inserted"

## Campos de Destino

| Bridge | Prioridad de destino |
|---|---|
| NAI Bridge | `nabPrompt` → `nabNegative` |
| ComfyUI Bridge | `cfbPrompt` → `cfbNegative` → `cfbWorkflowJson` |
| SD WebUI Bridge | `sdwbPrompt` → `sdwbNegative` |

## Permisos del Navegador

Esto utiliza la **API del Portapapeles** del navegador (`navigator.clipboard.readText()`),
por lo que el navegador puede solicitarte permiso de lectura del portapapeles en el primer uso.
Si lo denigas, la función no funcionará.

En navegadores más antiguos donde la API del Portapapeles no está disponible, se muestra un toast
"Clipboard API not available" y no ocurre nada. El pegado regular `Ctrl`+`V` continúa funcionando como antes.

## Limitaciones

- Algunos navegadores requieren HTTPS o `localhost` para que `navigator.clipboard` esté disponible
  (Chrome sí permite `localhost`)
- Solo se admite texto sin formato — no imágenes ni texto enriquecido
- Los elementos no `<textarea>` (p. ej. regiones `contenteditable`) no se dirigen
  aunque estén enfocados
