# Hailo LLM Auto-discovery

**Version supportée** : v4.66.0 et ultérieures

## Aperçu

yu_ai_manager peut découvrir automatiquement et utiliser les points de terminaison LLM s'exécutant sur le NPU Hailo du Pi5 sans modifier `config.json`. Il suffit de brancher un Pi5 sur le réseau local, et les autres nœuds yu_ai_manager peuvent appeler le Hailo LLM.

## Deux types de points de terminaison

| Point de Terminaison | Description | Motif d'URL par Défaut |
|---|---|---|
| **yu extension Hailo LLM** | LLM compatible OpenAI fourni par l'extension intégrée `builtin-hailo-genai` dans yu_ai_manager | `http://<host>:<yu-port>/ext/hailo-genai/v1/` |
| **hailo-ollama** | LLM compatible OpenAI fourni par le binaire externe `/usr/bin/hailo-ollama` (port par défaut `:8000`) | `http://<host>:8000/v1/` |

Les deux peuvent s'exécuter simultanément et les deux sont enregistrés automatiquement. Avec HailoRT 5.3.0+ et `HAILO_OLLAMA_VDEVICE_GROUP_ID=YU_SHARED` défini, le planificateur HailoRT partage l'appareil physique via round-robin, il n'y a donc pas de conflit lors de l'utilisation simultanée des deux.

## Enregistrement automatique local (Phase A)

Au démarrage, yu_ai_manager détecte indépendamment les deux points de terminaison suivants :

1. **yu extension** : Si `hailo_platform.genai.LLM` est importable et que `/dev/hailo0` ou `/dev/h1x-0` existe, il est enregistré automatiquement en tant que backend `hailo-local` dans le catalogue
   (v4.66.1 a ajouté la prise en charge de Raspberry Pi 5 + AI HAT + HailoRT 5.3.0 qui expose l'appareil en tant que `/dev/h1x-0`)
2. **hailo-ollama** : Une sonde HTTP est envoyée à `localhost:8000/v1/models` (délai d'expiration de 2 secondes). Si une réponse 200 est reçue, elle est enregistrée automatiquement en tant que backend `hailo-ollama-local`

Si un backend avec le même alias existe déjà dans `llm_router.backends` dans `config.json`, cette configuration a la priorité (elle ne sera pas écrasée).

## Annonce mDNS (Phase B)

En fonction des résultats de détection de la Phase A, yu_ai_manager annonce les capacités Hailo aux autres nœuds via les enregistrements TXT mDNS :

- `capabilities=llm,hailo` -- Indique que l'extension yu est disponible
- `hailo_ollama_url=http://192.168.1.10:8000/v1/` -- Inclus uniquement si hailo-ollama s'exécute (réécrit en une adresse IP accessible depuis le réseau local)

Lorsque d'autres nœuds yu_ai_manager reçoivent cela via mDNS, ils effectuent une vérification d'identité via le point de terminaison `/api/mdns/identity`, puis enregistrent automatiquement les backends supplémentaires avec les alias suivants :

- `mdns-<node_id[:8]>-hailo` -- Extension yu Hailo LLM (lorsque `capabilities` inclut `hailo`, l'URL est dérivée du `web_port` du peer + adresses)
- `mdns-<node_id[:8]>-hailo-ollama` -- hailo-ollama externe (lorsque `hailo_ollama_url` est annoncé, l'URL du registre TXT est utilisée telle quelle)

## Configuration

Activé par défaut. Vous pouvez le désactiver dans `config.json` comme suit :

```json
{
  "llm_router": {
    "hailo_ollama": {
      "enabled": false,
      "port": 8000
    }
  }
}
```

- **`enabled`** : Définissez à `false` pour désactiver complètement la détection automatique de hailo-ollama. La détection de l'extension yu est contrôlée séparément (déterminée automatiquement selon que l'extension est chargée)
- **`port`** : Numéro de port pour hailo-ollama (8000 par défaut). Les valeurs en dehors de la plage 1-65535 reviennent à la valeur par défaut avec un avertissement dans le journal

## Notes de sécurité

**hailo-ollama n'a pas d'authentification**. Lorsqu'il est annoncé via mDNS, **tout nœud sur le réseau local peut librement consommer les ressources d'inférence de hailo-ollama**.

| Point de Terminaison | Authentification | Exposition Efficace du Réseau Local |
|---|---|---|
| Extension yu (`/ext/hailo-genai/v1/`) | Chaîne d'authentification Web yu (PIN/session/clé API) | Uniquement les clients authentifiés avec yu |
| hailo-ollama (`hailo_ollama_url`) | **Aucune** | **Tous les nœuds sur le réseau local** |

Pour les environnements autres que les réseaux locaux domestiques ou les VLAN de confiance (par exemple, Wi-Fi public), désactivez la publicité automatique avec `hailo_ollama.enabled: false`.

## Apparence dans l'interface WebUI du routeur LLM

Les backends enregistrés automatiquement s'affichent sur le tableau de bord `/llm-router` (v4.65.0) :

- `hailo-local` / `hailo-ollama-local` -- Détecté localement (source : badge `static`)
- `mdns-<id>-hailo` / `mdns-<id>-hailo-ollama` -- Découvert via mDNS (source : badge `mdns`)

Tous peuvent être temporairement désactivés via le bouton de désactivation. L'état désactivé est conservé dans `data/llm_router_state.json` et conservé après les redémarrages (implémenté dans v4.65.0).

## Sécurité contre les faux positifs

La détection de la Phase A a deux mécanismes de sécurité :

1. **Évitement des sondes automatiques** : Si `hailo_ollama.port` est défini sur la même valeur que le port Web propre de yu, la sonde est complètement ignorée (empêche yu de se méconnaître comme hailo-ollama)
2. **Priorité du backend existant** : Si un backend avec le même `localhost:<port>/v1` est déjà enregistré dans `config.json`, la sonde est ignorée pour respecter l'intention de l'utilisateur

## Éléments TODO restants

- (P3) Traductions multilingues (`en`, `zh-tw`, `zh-cn`, `ko`) -- prévues pour être traitées en même temps que le travail en attente de traduction de l'interface WebUI LLM Router v4.65.0
- (P3) Tests d'intégration Pi5 -- Équivalent de 16 éléments Playwright dans une configuration à 2 nœuds
- (P3) Prise en charge IPv6 -- Actuellement `_pick_lan_ip` ne retourne que IPv4
- (P3) Prise en charge de plusieurs appareils Hailo -- Suppose un alias `hailo-local` fixe. La conception du suffixe d'index doit être envisagée pour les cas tels que plusieurs dongles USB
- (P3) `BackendCatalog.remove_backend()` -- Actuellement `_mark_unreachable` ne met à jour que l'état et ne supprime pas du catalogue

## Documentation associée

- [Configuration du routeur LLM](./setup.md)
- Spécification de conception : `docs/superpowers/specs/2026-04-08-hailo-auto-discovery-design.md`
- Plan de mise en œuvre : `docs/superpowers/plans/2026-04-08-hailo-auto-discovery.md`

## v4.66.2 -- Authentification de pair de confiance (Correction d'un vrai trou d'authentification)

Dans le Hailo auto-discovery de v4.66.0, l'extension `/ext/hailo-genai/*` de yu était derrière la chaîne d'authentification Web. Lorsque le pilote du routeur LLM (qui n'a ni jeton Bearer ni session) tentait de sonder/d'envoyer, l'intergiciel d'authentification renvoyait du HTML de leurre, ce qui causait des échecs d'analyse JSON et le backend restait bloqué en tant que `unreachable`.

### Comment ça marche

- Un nouveau `TrustedPeerRegistry` amorce `127.0.0.1` / `::1` au moment de l'initialisation
- Lorsque `LlmRouterMdnsBridge` vérifie avec succès un pair (HTTP GET à `/api/mdns/identity` + confirmation de correspondance node_id), toutes les adresses annoncées de ce pair sont ajoutées au registre
- `auth_chain.check_trusted_peer` contourne l'authentification PIN lors de la réception d'une demande pour les chemins `/ext/<name>/v1/*` si remote_addr est dans le registre
- Les chemins d'authentification par clé API / session / cookie existants restent inchangés

### Relation avec Quick Lock

- **loopback** (sonde propre de yu) : Passe toujours, même lors du quick_lock
- **IP du pair** : Les demandes sont rejetées lors du quick_lock (`check_quick_lock` retourne 503). Cela signifie que les pairs respectent également l'état "utilisateur verrouillé intentionnellement"

Ceci permet aux scénarios suivants de fonctionner comme prévu :

- Sonde propre `hailo-local` de pi2 (`http://localhost:5000/ext/hailo-genai/v1/models`)
- Envoi entre nœuds depuis Windows vers `mdns-<id>-hailo` de pi2 (`http://192.168.50.4:5000/ext/hailo-genai/v1/chat/completions`)

### Configuration

Aucune modification du fichier de configuration n'est nécessaire. Même dans les environnements où mDNS est désactivé, l'amorce de boucle locale fonctionne toujours, la correction de sonde propre est donc disponible sans condition.

### Débogage

Définissez la variable d'environnement `TAGDB_DEBUG_TRUSTED_PEERS=1` avant de démarrer yu pour ajouter un champ `trusted_ips` à la réponse `/api/mdns/peers`. Ne définissez pas cela en production (la liste de confiance est essentiellement une "liste de cibles d'attaque" et ne doit pas être exposée sur les points de terminaison non authentifiés).

### Limite de sécurité

Fonctionnement sous l'hypothèse du "réseau local de confiance" (même prémisse que v4.64.0 mDNS Phase B). La protection contre les nœuds malveillants ayant un accès physique au réseau local est hors de portée -- utilisez le bouton de désactivation de l'interface WebUI `/llm-router` ou quick_lock pour ces cas.

Voir `docs/superpowers/specs/2026-04-09-trusted-peer-auth-design.md` pour les détails.
