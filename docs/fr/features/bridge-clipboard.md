# Raccourci Presse-papiers Bridge

Sur les pages NAI Bridge / ComfyUI Bridge / SD WebUI Bridge, un raccourci clavier vous permet
d'envoyer instantanément le texte du presse-papiers dans le champ de prompt. Quand vous avez copié un prompt
d'une autre fenêtre, vous pouvez l'appliquer sans d'abord cliquer dans la textarea.

## Raccourci

| OS | Touches |
|---|---|
| Windows / Linux | `Ctrl` + `Alt` + `V` |
| macOS | `⌘` + `⌥` + `V` |

Ceci est ajouté à côté du collage natif du navigateur (`Ctrl`+`V`) et n'interfère pas
avec le comportement de collage existant.

## Comportement

1. Ouvrir l'une des pages Bridge
2. Copier du texte d'une source externe (`Ctrl`+`C`)
3. Appuyer sur `Ctrl`+`Alt`+`V` tandis que la page Bridge a le focus
4. Sélection de la cible :
   - Si une textarea est focus → inséré à la position du curseur dans cette textarea
   - Si rien n'est focus → inséré dans le champ de prompt positif (NAI : `#nabPrompt` / ComfyUI : `#cfbPrompt` / SD : `#sdwbPrompt`)
5. En cas de succès, un toast "Clipboard text inserted" est affiché

## Champs cibles

| Bridge | Priorité cible |
|---|---|
| NAI Bridge | `nabPrompt` → `nabNegative` |
| ComfyUI Bridge | `cfbPrompt` → `cfbNegative` → `cfbWorkflowJson` |
| SD WebUI Bridge | `sdwbPrompt` → `sdwbNegative` |

## Permissions du navigateur

Ceci utilise l'**API Clipboard** du navigateur (`navigator.clipboard.readText()`),
donc le navigateur peut vous demander la permission de lecture du presse-papiers à la première utilisation.
Si vous la refusez, la fonctionnalité ne fonctionnera pas.

Sur les navigateurs plus anciens où l'API Clipboard n'est pas disponible, un toast "Clipboard
API not available" est affiché et rien ne se passe. Le collage `Ctrl`+`V` normal
continue de fonctionner comme avant.

## Limitations

- Certains navigateurs nécessitent HTTPS ou `localhost` pour que `navigator.clipboard` soit
  disponible (Chrome autorise `localhost`)
- Seul le texte brut est pris en charge — pas les images ou le texte enrichi
- Les éléments non-`<textarea>` (par ex. les régions `contenteditable`) ne sont pas ciblés
  même quand ils ont le focus
