# Interface WebUI du routeur LLM

Un tableau de bord administrateur accessible à `/llm-router`. Il vous permet de vérifier l'état des backends enregistrés et de les activer/désactiver.

---

## Disposition de la page

```
┌─────────────────────────────────────┐
│  🤖 LLM Router          [Refresh All] │
├─────────┬─────────┬────────┬─────────┤
│Backends │ Enabled │ Models │ Aliases │  ← Summary cards
├─────────┴─────────┴────────┴─────────┤
│  Backends table                      │
├───────────────────────────────────────┤
│  Routing Aliases table               │
└───────────────────────────────────────┘
```

### Cartes de synthèse (4)

| Carte | Contenu |
|---|---|
| **Backends** | Nombre total de backends enregistrés dans le catalogue |
| **Enabled** | Nombre de backends qui ne sont pas désactivés |
| **Models** | Nombre total de modèles exposés par tous les backends |
| **Routing aliases** | Nombre d'alias définis dans le fichier de configuration |

Les valeurs des cartes sont automatiquement rendues en récupérant `/api/llm_router/status` au chargement de la page.

---

## Table des backends

Chaque ligne correspond à un seul backend physique (par exemple, une instance Ollama).

### Descriptions des colonnes

| Colonne | Description |
|---|---|
| **Alias** | Un nom court unique identifiant le backend (par exemple, `ollama-mac`, `mdns-pi5-hailo`). Utilisé comme clé pour la configuration du routage et la résolution d'alias |
| **Base URL** | L'URL de base du point de terminaison compatible OpenAI du backend (par exemple, `http://192.168.1.10:11434`) |
| **Status** | État de connectivité du backend. Voir les détails ci-dessous |
| **SLO** | État de charge des ressources du backend (`vision_idle` / `vision_active` / `unknown`). Utilisé pour les backends Hailo Vision |
| **Models** | Nombre de modèles récupérés lors de la dernière sonde. Peut être extensible pour afficher une liste détaillée selon l'implémentation |
| **Last Seen** | Date et heure de la dernière réponse réussie (ISO 8601). `null` si aucune réponse réussie n'a jamais été reçue |
| **Actions** | Boutons d'action par backend (voir ci-dessous) |

### Valeurs de statut

| Valeur | Signification |
|---|---|
| `ready` | La dernière sonde a réussi et la liste des modèles a été récupérée |
| `unreachable` | Un délai d'attente ou une erreur de connexion s'est produit |
| `unknown` | Aucune sonde n'a encore été exécutée (par exemple, juste après le démarrage) |
| `probing` | Une sonde est actuellement en cours d'exécution (peut apparaître brièvement dans l'interface lors d'une actualisation) |

> **Conseil**: Les backends `unreachable` sont exclus du routage mais restent dans le catalogue. Après la récupération du réseau, exécutez Refresh All ou une actualisation individuelle pour les restaurer à `ready`.

### Valeurs SLO

| Valeur | Signification |
|---|---|
| `vision_idle` | La tâche Vision est inactive. La charge du LLM est faible |
| `vision_active` | Une tâche Vision est en cours d'exécution. Le routeur LLM peut prioriser d'autres backends |
| `unknown` | Les informations SLO ne sont pas disponibles (backend non-Hailo, ou la récupération a échoué) |

---

## Bouton Refresh All

Cliquez sur **Refresh All** en haut à droite pour forcer une sonde sur tous les backends, en mettant à jour leurs listes de modèles et leurs états.

- Le bouton est désactivé pendant l'exécution et la page est re-rendue à l'achèvement
- Comportement interne: Appelle `POST /api/llm_router/refresh` (pas de body) pour exécuter `discover_all` pour tous les backends
- Les actualisations individuelles du backend peuvent être disponibles via un bouton Refresh dans la colonne Actions (dépend de l'implémentation)

---

## Désactivation / Activation de backends individuels

### Étapes

1. Regardez la colonne **Actions** dans le tableau des backends
2. Cliquez sur le bouton **Disable** sur la ligne du backend que vous souhaitez désactiver
3. Le bouton devient **Enable** et la ligne est grisée
4. Pour réactiver, cliquez sur **Enable**

### Comportement et persistance

- Les modifications sont immédiatement reflétées dans le catalogue en mémoire
- Simultanément, une écriture atomique est effectuée sur `data/llm_router_state.json`

  ```json
  {
    "version": 1,
    "disabled_aliases": ["ollama-slow", "mdns-pi5"]
  }
  ```

- L'état désactivé est préservé entre les redémarrages de l'application
- Si un backend découvert par mDNS était désactivé avant le démarrage, l'état désactivé est automatiquement appliqué après la découverte (mécanisme `_pending_disabled`)
- Si l'écriture échoue, l'état en mémoire est annulé pour éviter l'incohérence avec le disque

### Comportement des backends désactivés

- Exclus du routage dans les points de terminaison compatibles OpenAI tels que `/v1/chat/completions`
- Le routage direct vers un backend désactivé retourne `503 Service Unavailable`
- Les backends désactivés apparaissent toujours dans le tableau WebUI (pour la visibilité de l'état et la réactivation)

---

## Table d'alias de routage

Affiche le mappage entre les noms de modèle logiques et les ID de modèle physiques tels que définis dans le fichier de configuration.

| Colonne | Description |
|---|---|
| **Alias** | Le nom logique que les clients spécifient dans le paramètre `model` (par exemple, `default-llm`, `fast-chat`) |
| **Physical Model** | L'ID de modèle physique qui traite réellement la demande (format: `backend-alias/model-name`, par exemple, `ollama-mac/qwen2.5:7b`) |

### Rôle des alias

Les alias vous permettent de basculer les backends ou les modèles sans modifier le code client.

- Les clients envoient des demandes en utilisant un nom logique comme `"model": "default-llm"`
- Le routeur LLM résout `default-llm → ollama-mac/qwen2.5:7b` et proxifie la demande
- Lors de la migration d'un backend vers une autre machine, il suffit de changer la cible de l'alias

Les alias sont définis statiquement dans le fichier de configuration, et l'interface WebUI les affiche en mode lecture seule. Les modifications nécessitent d'éditer le fichier de configuration et de redémarrer l'application.

---

## Opérations courantes

### Quand un backend est inaccessible

1. Vérifiez que le service backend (Ollama, etc.) s'exécute
2. Exécutez **Refresh All** ou une actualisation individuelle
3. Si le problème persiste, vérifiez les détails de l'erreur dans la colonne `last_error` (ou la réponse API)

### Désactivation permanente d'un backend découvert par mDNS

1. Cliquez sur **Disable** dans la colonne Actions du backend cible
2. L'alias est enregistré dans `data/llm_router_state.json`, il reste donc désactivé même après la redécouverte

### Arrêt temporaire de la charge sur un backend spécifique

Utilisez **Disable** pour l'exclure immédiatement du routage, puis **Enable** pour le restaurer quand vous avez terminé. Aucun redémarrage n'est nécessaire.
