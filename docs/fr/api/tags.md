# API Étiquettes

API pour les opérations d'étiquette par lot et les suggestions/autocomplétion d'étiquettes.

## POST /api/tags/batch-set

Ajouter ou supprimer des étiquettes de plusieurs fichiers en une seule requête.

### Limitation de débit

WRITE (~120 req/min, burst 30)

### Corps de la requête

| Champ | Type | Requis | Description |
|-------|------|--------|-------------|
| `items` | array | Oui | Liste des opérations (max 500 éléments) |
| `items[].file_id` | int | Oui | ID du fichier (entier positif) |
| `items[].add` | string[] | Non | Noms d'étiquette à ajouter |
| `items[].remove` | string[] | Non | Noms d'étiquette à supprimer |

- Chaque élément nécessite au moins l'un de `add` ou `remove`
- Les étiquettes qui n'existent pas sont créées automatiquement (namespace=null)
- Les étiquettes ajoutées via API ont leur source définie sur `"user"`
- Les étiquettes orphelines (pas d'associations de fichiers restantes) sont supprimées automatiquement

### Exemple de requête

```json
{
  "items": [
    {
      "file_id": 42,
      "add": ["landscape", "sunset"],
      "remove": ["lowres"]
    }
  ]
}
```

### Réponse

```json
{
  "total": 1,
  "succeeded": 1,
  "failed": 0,
  "errors": []
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `total` | int | Nombre total d'éléments traités |
| `succeeded` | int | Nombre d'opérations réussies |
| `failed` | int | Nombre d'opérations échouées |
| `errors` | array | Liste des détails d'erreur |

### Erreurs

| Statut | Description |
|--------|-------------|
| 400 | Corps de requête invalide (éléments vides, file_id invalide, add/remove manquants, etc.) |
| 429 | Limitation de débit dépassée |

---

## GET /api/tags/suggest

Retourner les candidats d'étiquette correspondant à une chaîne de recherche partielle. Destiné à l'autocomplétion.

### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| `q` | string | Oui | Chaîne de recherche |
| `limit` | int | Non | Nombre maximum de résultats (par défaut : 20, max : 100) |

- La recherche est insensible à la casse (LIKE %q%)
- Les résultats sont triés par `file_count` en ordre décroissant
- Un `q` vide retourne un tableau vide

### Réponse

```json
{
  "data": [
    { "id": 1, "tag": "landscape", "namespace": null, "file_count": 150 },
    { "id": 2, "tag": "1girl", "namespace": null, "file_count": 3420 }
  ]
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `data[].id` | int | ID de l'étiquette |
| `data[].tag` | string | Nom de l'étiquette |
| `data[].namespace` | string\|null | Namespace (généralement null) |
| `data[].file_count` | int | Nombre de fichiers associés à cette étiquette |
