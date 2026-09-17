# Guide de recherche

Trouvez vos images rapidement avec des filtres puissants.

## Syntaxe de base

```
keyword1 keyword2
```

Recherche les images contenant les deux mots-clés.

## Filtres

### Format

```
format:jpg
format:png
format:gif
```

### Date

```
date:2026-01
date:2025-12-25
date>2025-01-01
date<2026-01-01
```

### Notation

```
rating:5
rating>=4
rating<3
```

### Collections

```
collection:"Ma collection"
```

### Texte dans les prompts

```
in_prompt:"text"
```

## Opérateurs

| Opérateur | Signification |
|-----------|--------------|
| `AND` ou espace | ET logique |
| `OR` | OU logique |
| `-` | Exclusion |

## Exemples

```
chat noir format:jpg rating>=4
cheval -âne
cat OR dog
prompt:"landscape"
```

## Recherche sémantique

YU AI Manager supporte la recherche sémantique basée sur CLIP. Tapez une description naturelle pour trouver des images similaires :

```
un coucher de soleil sur l'océan
```

## Conseils de performance

- Commencez par des mots-clés généraux et affinez
- Utilisez des filtres de date pour réduire l'ensemble de résultats
- Groupez par dossier pour une navigation plus rapide

Consultez la [documentation API de recherche](../../api/search.md) pour plus de détails.
