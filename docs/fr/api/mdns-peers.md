# API : /api/mdns (Découverte des pairs)

> Version cible : v4.64.0 et ultérieures (Extensions Hailo : v4.66.0 et ultérieures)

API permettant aux nœuds yu_ai_manager sur un LAN de se découvrir mutuellement via mDNS (`_yu-ai._tcp.local.`). Il y a deux points d'accès.

---

## GET /api/mdns/identity

### Aperçu

Un point d'accès de présentation automatique pour un nœud. Les autres nœuds l'appellent lors de la vérification des pairs pour confirmer que les informations annoncées via mDNS appartiennent à une instance yu_ai_manager authentique.

### Authentification

**Contournement d'authentification (non requis).** L'authentification est intentionnellement omise car ce point d'accès est utilisé pour la vérification mutuelle des pairs. La réponse contient uniquement les informations déjà publiquement disponibles via mDNS. Aucun secret ou information sensible n'est inclus.

### Réponse

```json
{
  "product": "yu_ai_manager",
  "node_id": "a1b2c3d4-...",
  "version": "4.66.0",
  "capabilities": ["hailo"],
  "hailo_ollama_url": "http://192.168.1.10:11434"
}
```

| Champ | Type | Description |
|---|---|---|
| `product` | string | Toujours `"yu_ai_manager"` |
| `node_id` | string | UUID unique du nœud |
| `version` | string | Version de l'application (lue dans le fichier VERSION) |
| `capabilities` | string[] | Liste des capacités disponibles. Actuellement uniquement `"hailo"` |
| `hailo_ollama_url` | string (optionnel) | URL d'accès LAN pour Hailo-Ollama. Non inclus si l'IP LAN ne peut pas être déterminé |

**Condition pour que `capabilities` inclue `"hailo"` :** Le backend `"hailo-local"` est enregistré dans le catalogue du LLM Router.

**Condition pour que `hailo_ollama_url` soit inclus :** Le backend `"hailo-ollama-local"` est enregistré dans le catalogue et une IP LAN peut être déterminée. Les adresses loopback (`127.0.0.1`, etc.) sont réécrites vers l'IP LAN.

---

## GET /api/mdns/peers

### Aperçu

Retourne une liste des pairs LAN découverts par ce nœud. Destiné à la vérification de l'état du sous-système mDNS et au débogage.

### Authentification

**Contournement d'authentification (non requis).** La réponse contient uniquement les informations déjà diffusées sur le LAN via mDNS.

### Réponse (Normal)

```json
{
  "running": true,
  "status": "browsing",
  "self_node_id": "a1b2c3d4-...",
  "peers": [
    {
      "node_id": "e5f6a7b8-...",
      "hostname": "raspberrypi.local",
      "version": "4.66.0",
      "llm_base_url": "http://192.168.1.20:11434",
      "llm_provider": "ollama",
      "capabilities": ["hailo"],
      "web_port": 5000,
      "addresses": ["192.168.1.20"],
      "hailo_ollama_url": "http://192.168.1.20:11434",
      "first_seen": 1712600000.0,
      "last_seen": 1712603600.0
    }
  ]
}
```

| Champ | Type | Description |
|---|---|---|
| `running` | bool | Si le sous-système mDNS est en cours d'exécution |
| `status` | string | Chaîne de statut du sous-système |
| `self_node_id` | string | node_id de ce nœud |
| `peers` | object[] | Liste des pairs découverts (voir tableau ci-dessous) |

**Éléments des pairs :**

| Champ | Type | Description |
|---|---|---|
| `node_id` | string | UUID unique du pair |
| `hostname` | string | Nom d'hôte mDNS |
| `version` | string | Version de l'application du pair |
| `llm_base_url` | string \| null | URL du point d'accès LLM du pair |
| `llm_provider` | string \| null | Nom du fournisseur LLM (par ex. `"ollama"`) |
| `capabilities` | string[] | Liste des capacités du pair |
| `web_port` | int \| null | Port WebUI du pair |
| `addresses` | string[] | Adresses IP LAN du pair |
| `hailo_ollama_url` | string \| null | URL Hailo-Ollama du pair |
| `first_seen` | float \| null | Heure de la première découverte (timestamp Unix) |
| `last_seen` | float \| null | Heure de la dernière vérification (timestamp Unix) |

### Réponse (mDNS Non initialisé)

```json
{
  "running": false,
  "reason": "mdns subsystem not initialised (disabled or init failed)",
  "peers": []
}
```

Quand `running: false`, mDNS est soit désactivé, soit l'initialisation a échoué. Vérifiez la configuration et les journaux de démarrage.

---

## Mode débogage

Démarrez yu avec la variable d'environnement `TAGDB_DEBUG_TRUSTED_PEERS=1` pour inclure des champs supplémentaires dans la réponse `/api/mdns/peers`.

```json
{
  "running": true,
  "peers": [...],
  "trusted_ips": ["192.168.1.20", "192.168.1.30"],
  "bridge": {
    "managed_aliases": ["ollama-192.168.1.20"],
    "config_aliases": ["my-nas"],
    "cooldown_seconds_remaining": {
      "e5f6a7b8": 12.3
    }
  }
}
```

| Champ | Description |
|---|---|
| `trusted_ips` | Liste des IP enregistrées dans le registre des IP de confiance |
| `bridge.managed_aliases` | Liste des alias gérés par le pont mDNS |
| `bridge.config_aliases` | Liste des alias définis de manière statique dans config |
| `bridge.cooldown_seconds_remaining` | Secondes de refroidissement restantes indexées par les 8 premiers caractères du node_id |

**Avertissement :** `trusted_ips` pourrait servir de cible d'attaque, donc il n'est pas exposé par défaut. Ne définissez pas `TAGDB_DEBUG_TRUSTED_PEERS=1` dans les environnements de production.

---

## Flux de découverte mDNS

```
L'autre nœud démarre
    │
    ▼
Annonce mDNS _yu-ai._tcp.local.
    │
    ▼
LlmRouterMdnsBridge reçoit on_peer_added()
    │
    ▼
Vérification HTTP via GET /api/mdns/identity
    │
    ├─ Succès → S'enregistrer dans PeerRegistry / BackendCatalog
    └─ Échec → Réessayer après refroidissement
```

---

## Fichiers connexes

- `routes/mdns_identity.py` -- Implémentation du point d'accès
- `core/mdns/` -- Utilitaires de service mDNS / adresse
- `core/llm_router/state.py` -- BackendCatalog
- `core/web/trusted_peer_registry.py` -- Registre des IP de confiance
- `docs/en/mesh-inference/overview.md` -- Architecture globale de l'inférence mesh
