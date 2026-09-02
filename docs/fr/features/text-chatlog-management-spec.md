# Spécification de gestion du texte et du journal de discussion YU AI Manager

Créé : 2026-03-01
Version cible : À déterminer (calendrier d'implémentation en cours d'examen)

## Aperçu

Trois fonctionnalités sont ajoutées à YU AI Manager :

- **Visionneuse MD** — Affichage local des fichiers Markdown
- **Gestion des journaux de discussion** — Importer, afficher et rechercher les journaux à partir de Claude/ChatGPT/Open WebUI
- **Recherche de texte intégral** — Recherche inter-contenu alimentée par FTS5

La philosophie de conception est la même que les fonctionnalités existantes : « complètement local, sans dépendance cloud ».

---

## 1. Visionneuse MD

### Objectif

Les visionneuses de fichiers OS offrent un rendu Markdown médiocre. Cette fonctionnalité apporte le rendu Markdown entièrement dans YU AI Manager, servant d'outil de référence quotidien pour les notes de développement, les documents de conception et les listes TODO.

### Cibles de scan

- Extensions : `.md`, `.markdown`
- Les racines de scan existantes sont réutilisées
- Exclues : les fichiers sous `.git/` et `node_modules/`

### Schéma DB

```sql
CREATE TABLE md_files (
    id          INTEGER PRIMARY KEY,
    path        TEXT NOT NULL UNIQUE,
    mtime       INTEGER NOT NULL,
    size        INTEGER NOT NULL,
    title       TEXT,        -- Extrait de la première # heading
    content     TEXT,        -- Texte Markdown brut
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    indexed_at  INTEGER
);

CREATE VIRTUAL TABLE md_files_fts USING fts5(
    title,
    content,
    content='md_files',
    content_rowid='id'
);
```

### Interface utilisateur de la visionneuse

- Intégrée dans le modal existant ou le panneau latéral
- Rendu : marked.js (groupé localement, pas de CDN)
- Blocs de code : coloration syntaxique (highlight.js)
- Un bouton de basculement de vue texte brut est fourni

### Support MCP

- `search_md_files(query, path_filter)` -> liste de fichiers
- `get_md_content(file_id)` -> texte brut

---

## 2. Gestion des journaux de discussion

### Objectif

Cette fonctionnalité sert de moteur de recherche pour l'historique de développement, permettant de trouver les discussions passées en utilisant des mots-clés vagues. Exemples : « Où était cette discussion de bug ? » ou « Quelle était la raison de cette décision de conception ? »

### Formats pris en charge

| Service | Format d'exportation | Comment obtenir |
|---|---|---|
| Claude | conversations.json | Paramètres -> Exporter les données |
| ChatGPT | conversations.json | Paramètres -> Exporter les données |
| Open WebUI | Export JSON | Historique des discussions -> Exporter |

### Schéma DB

```sql
-- Par conversation
CREATE TABLE chat_conversations (
    id            INTEGER PRIMARY KEY,
    source        TEXT NOT NULL,  -- 'claude' / 'chatgpt' / 'openwebui'
    external_id   TEXT,           -- ID de conversation du service original
    title         TEXT,
    model         TEXT,           -- Nom du modèle utilisé
    created_at    INTEGER,
    updated_at    INTEGER,
    message_count INTEGER,
    imported_at   INTEGER NOT NULL
);

-- Par message
CREATE TABLE chat_messages (
    id              INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id),
    role            TEXT NOT NULL,  -- 'user' / 'assistant' / 'system'
    content         TEXT NOT NULL,
    created_at      INTEGER,
    seq             INTEGER         -- Ordre dans la conversation
);

-- Recherche de texte intégral FTS5
CREATE VIRTUAL TABLE chat_messages_fts USING fts5(
    content,
    content='chat_messages',
    content_rowid='id',
    tokenize='unicode61'
);
```

### Importateur

Le JSON de chaque service est converti en un format intermédiaire commun et inséré dans la DB.

**Structure JSON Claude (champs clés) :**

```json
{
  "uuid": "...",
  "name": "Titre de la conversation",
  "created_at": "2026-01-01T00:00:00Z",
  "chat_messages": [
    {"role": "human", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

**Structure JSON ChatGPT (champs clés) :**

```json
{
  "id": "...",
  "title": "Titre de la conversation",
  "create_time": 1234567890,
  "mapping": {
    "node_id": {
      "message": {
        "author": {"role": "user"},
        "content": {"parts": ["..."]}
      }
    }
  }
}
```

**Structure JSON Open WebUI :**

- Suit le format API compatible OpenAI
- Tableau de messages avec role/content

### Interface utilisateur d'importation

- Une section d'importation est ajoutée à la page des paramètres
- Les fichiers JSON peuvent être glissés via glisser-déposer ou sélectionnés avec un sélecteur de fichier
- Les conversations précédemment importées sont dédupliquées par `external_id` (idempotent)
- Un résumé d'importation (nombre ajouté et nombre ignoré) est affiché

### Interface utilisateur de la visionneuse

- Page de liste de conversations (titre, date, modèle, source)
- Page de détail de la conversation (affichage basé sur les tours avec codage de couleur basé sur le rôle)
- Filtres par nom de modèle, source et plage de dates
- Les images jointes stockent uniquement les références de chemin (pas de copies de fichiers)

### Support MCP

- `search_chat_logs(query, source, model, date_from, date_to)` -> liste de conversations
- `get_conversation(conversation_id)` -> liste de messages
- `import_chat_log(source, json_path)` -> exécuter l'importation

---

## 3. Recherche de texte intégral

### Cibles

- Fichiers MD (`md_files_fts`)
- Journaux de discussion (`chat_messages_fts`)
- Bibliothèque de prompts existante (`prompt_library_fts`, déjà implémentée)

### Interface utilisateur de recherche

- Soit étendre la barre de recherche existante, soit fournir une page de recherche de texte dédiée
- Basculer les cibles de recherche (MD / chatlog / bibliothèque de prompts)
- Résultats classés par score BM25
- Affichage d'extrait avec succès (~50 caractères de contexte environnant)

### API de recherche

```
GET /api/text-search?q=keyword&target=md,chat,prompt&limit=20
```

Réponse :

```json
{
  "results": [
    {
      "type": "chat",
      "conversation_id": 123,
      "title": "Titre de la conversation",
      "snippet": "...texte autour du succès...",
      "score": 0.95,
      "date": "2026-01-01"
    }
  ]
}
```

---

## Priorité de mise en œuvre

1. Visionneuse MD (faible coût de mise en œuvre, valeur immédiate élevée)
2. Importateur de journaux de discussion (support Claude/ChatGPT en premier)
3. Visionneuse de journaux de discussion
4. Support Open WebUI
5. Interface utilisateur de recherche de texte inter-contenu

---

## Extensions futures

- Importation automatique et périodique du journal de discussion (placer les fichiers d'exportation dans un dossier surveillé pour l'ingestion automatique)
- Lier les prompts de génération d'images aux discussions du journal de discussion qui les ont produites
- Résumé et étiquetage automatiques du journal de discussion via Ollama

---

## Notes

- Les modèles FTS5 peuvent être réutilisés à partir de l'implémentation existante `prompt_library_fts`
- marked.js est groupé localement plutôt que chargé à partir d'un CDN (conformément à la philosophie de conception locale uniquement)
- Les images jointes dans les journaux de discussion (images générées par DALL-E, etc.) ne sont pas enregistrées localement car leurs URL expirent
