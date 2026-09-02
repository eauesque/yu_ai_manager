# API Rastérisation SVG

API pour convertir des images vectorielles SVG en bitmaps PNG/WebP.
Conçue pour l'intégration du pipeline img2img — les données d'image base64 retournées peuvent être passées directement à NAI Bridge ou SD WebUI Bridge.

## GET /api/svg/info

Vérifier la disponibilité de la rastérisation SVG.

- **Limitation de débit** : Aucune (GET)

### Réponse

```json
{
  "available": true,
  "backend": "resvg"
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `available` | bool | Si la rastérisation est disponible |
| `backend` | string \| null | Backend actif (`"resvg"` ou `null`) |

---

## POST /api/svg/rasterize

Rastériser un SVG en un bitmap PNG/WebP.

- **Limitation de débit** : HEAVY

### Corps de la requête

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `file_id` | int | *1 | ID du fichier SVG de la base de données |
| `svg_path` | string | *1 | Chemin absolu vers un fichier SVG |
| `svg_data` | string | *1 | Chaîne XML SVG en ligne |
| `width` | int | Non | Largeur de sortie (par défaut : 1024) |
| `height` | int | Non | Hauteur de sortie (par défaut : 1024) |
| `format` | string | Non | `"png"` ou `"webp"` (par défaut : `"png"`) |
| `background` | string | Non | Couleur de fond (par ex. `"#ffffff"`). Transparent si omis |

> *1 : Fournissez exactement l'un de `file_id`, `svg_path` ou `svg_data`.

### Exemple de requête

```json
{
  "file_id": 123,
  "width": 832,
  "height": 1216,
  "format": "png",
  "background": "#ffffff"
}
```

### Réponse

```json
{
  "ok": true,
  "base64": "iVBORw0KGgo...",
  "width": 832,
  "height": 1216,
  "format": "png",
  "size_bytes": 45678
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `ok` | bool | Drapeau de succès |
| `base64` | string | Données PNG/WebP encodées en base64 |
| `width` | int | Largeur de sortie réelle |
| `height` | int | Hauteur de sortie réelle |
| `format` | string | Format de sortie |
| `size_bytes` | int | Taille binaire en octets |

### Réponse d'erreur

```json
{
  "ok": false,
  "error": "resvg is not installed (pip install resvg)"
}
```

---

## Intégration MCP

Utilisez Claude Desktop pour construire un pipeline SVG → img2img :

```
# Étape 1 : Rastériser le SVG
svg_rasterize(file_id=123, width=832, height=1216, background="#ffffff")

# Étape 2 : Passer la base64 retournée à img2img
nai_generate(prompt="icon, detailed illustration, ...", image=<base64>, strength=0.7)
```

### Outils MCP

| Outil | Description |
|-------|-------------|
| `svg_info` | Vérifier la disponibilité de la rastérisation |
| `svg_rasterize` | Rastériser SVG en PNG/WebP |

---

## Dépendances

| Package | Licence | Objectif |
|---------|---------|---------|
| `resvg` | MIT | Moteur de rendu SVG basé sur Rust (multiplateforme) |

Si `resvg` n'est pas installé, les miniatures affichent un placeholder et l'API retourne HTTP 501.

```bash
pip install resvg
```
