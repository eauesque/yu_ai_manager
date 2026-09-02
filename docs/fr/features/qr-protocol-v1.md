# Protocole YU QR v1 — Spécification unifiée de la charge utile

**Version :** 1.0
**Date :** 2026-02-23
**Application cible :** YU AI Manager (TagDB)

---

## Aperçu

YU AI Manager supporte le partage de prompts et le diagnostic des erreurs via des codes QR.
Ce document fournit une spécification unifiée pour le format de charge utile QR.

### Bibliothèques utilisées

| Objectif | Bibliothèque | Version |
|------|-----------|-----------|
| Génération QR | QRCode.js | 1.0.0 |
| Lecture QR | jsQR | 1.4.0 |

### Limites de capacité QR

- Nombre maximum de caractères : **2,953** (niveau de correction d'erreur M)
- Au-delà de 2,500 caractères : le JSON méta est minifié et réessayé
- Au-delà de 2,953 caractères : erreur (`qr.info.too_long`)

---

## Type de charge utile 1 — Partage de prompt

### Origine

- `GET /api/share/<file_id>` -> Python `build_share_data_payload()`
- `routes/share_ops/payload_build.py`

### Schéma JSON

```json
{
  "v":   "1.0",
  "t":   "prompt",
  "p":   "<positive prompt>",
  "n":   "<negative prompt>",
  "src": "TagDB",
  "m":   "<model name>",
  "s":   "<seed>",
  "st":  "<steps>",
  "cfg": "<CFG scale>",
  "sa":  "<sampler>",
  "sz":  "<WxH>"
}
```

### Définitions des champs

| Clé | Type | Requise | Description | Limite |
|------|-----|------|------|------|
| `v` | string | ✅ | Version du protocole. Actuellement `"1.0"` | — |
| `t` | string | ✅ | Type de charge utile. Actuellement toujours `"prompt"` | — |
| `p` | string | ✅ | Prompt positif | 2 000 caractères |
| `n` | string | ✅ | Prompt négatif | 1 000 caractères |
| `src` | string | ✅ | Identifiant de l'émetteur. Actuellement toujours `"TagDB"` | — |
| `m` | string | — | Nom du modèle | — |
| `s` | string | — | Valeur de seed | — |
| `st` | string | — | Nombre d'étapes | — |
| `cfg` | string | — | Échelle CFG | — |
| `sa` | string | — | Nom du sampler | — |
| `sz` | string | — | Taille d'image au format `"WxH"` | — |

---

## Modes QR — 4 types

### Mode `positive`

```
qrText = shareData.p
```

- Contenu : Texte du prompt positif uniquement
- Cas d'usage : Partage de texte direct des prompts

### Mode `negative`

```
qrText = shareData.n
```

- Contenu : Texte du prompt négatif uniquement

### Mode `meta`

```
qrText = JSON.stringify(shareData, null, 0)
```

- Contenu : La charge utile JSON complète de partage de prompt, compactée
- Revient à `JSON.stringify` bien formaté quand le résultat dépasse 2 500 caractères

### Mode `url`

```
encoded = btoa(unescape(encodeURIComponent(JSON.stringify(shareData))))
qrText  = "{origin}/share?data={encoded}"
```

- Contenu : Une URL vers la page de partage YU AI Manager
- Désactivé sur localhost (`localhost` / `127.0.0.1`)

---

## Type de charge utile 2 — Diagnostic d'erreur

### Origine

- Généré sur les erreurs HTTP -> `_render_error_page()`
- `core/web/app_factory_handlers.py`

### Schéma JSON

```json
{
  "s": "<HTTP status code>",
  "p": "<request path>",
  "v": "<APP_VERSION>"
}
```

### Définitions des champs

| Clé | Type | Description | Limite |
|------|-----|------|------|
| `s` | string | Code de statut HTTP (`"404"`, `"500"`, etc.) | — |
| `p` | string | Chemin de la requête | 80 caractères |
| `v` | string | Version de l'application (à partir du fichier `APP_VERSION`) | — |

---

## Procédure de décodage du partage URL

Décodage sur la page de partage (`/share?data=...`) :

```javascript
const encoded = new URL(location).searchParams.get('data');
const json    = decodeURIComponent(escape(atob(encoded)));
const data    = JSON.parse(json);
```

---

## Paramètres de génération QR

```javascript
new QRCode(container, {
  text:         qrText,
  width:        200,   // 180 on error pages
  height:       200,   // 180 on error pages
  colorDark:    '#000000',
  colorLight:   '#ffffff',
  correctLevel: QRCode.CorrectLevel.M,  // 15% error correction
});
```

---

## Extensions futures (v1.x)

| Fonctionnalité | Statut | Remarques |
|------|------|------|
| Export QR de collection (images multiples) | Non implémenté | Prévu comme type de charge utile 3 |
| Type `t: "collection"` | Non défini | Liste des ID fichier + nom de collection |
| Compression (gzip + Base64) | Non implémenté | Alternative pour les prompts dépassant 2 953 caractères |

---

## Fichiers d'implémentation

| Fichier | Rôle |
|----------|------|
| `routes/share.py` | Blueprint Share API |
| `routes/share_ops/payload_build.py` | Génération de charge utile |
| `routes/share_ops/prompt_extract.py` | Extraction de données de prompt |
| `core/web/app_factory_handlers.py` | Génération de données QR d'erreur |
| `static/js/runtime/tools/runtime-tools-qr-core.js` | Construction et rendu QR |
| `static/js/runtime/tools/runtime-tools-qr.js` | Gestionnaires d'interface utilisateur QR |
| `static/js/share/share-qr.js` | Décodage d'image QR |
| `static/js/share/share-page.js` | Affichage de la page de partage |
| `static/vendor/qrcode.min.js` | Bibliothèque QRCode.js |
| `static/vendor/jsQR.min.js` | Bibliothèque jsQR |
