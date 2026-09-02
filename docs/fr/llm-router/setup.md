# Configuration du routeur LLM

## Ajout à config.json

```json
{
  "llm_router": {
    "enabled": true,
    "auth": {
      "mode": "loopback",
      "api_key": "",
      "allow_loopback_bypass": true
    },
    "backends": [
      {
        "alias": "ollama-local",
        "base_url": "http://localhost:11434/v1",
        "type": "ollama",
        "auto_discover": true
      }
    ],
    "aliases": {
      "local-fast": "ollama-local/qwen2.5:7b",
      "local-coder": "ollama-local/qwen2.5-coder:32b"
    }
  }
}
```

## Intégration avec Claude Code

```bash
ANTHROPIC_BASE_URL=http://localhost:5000/v1 claude
```

Lors de l'envoi de requêtes, spécifiez un alias ou un nom physique dans le champ `model`:
- `local-fast` (alias)
- `ollama-local/qwen2.5:7b` (nom physique)

## Intégration avec Continue (VSCode)

`config.json`:
```json
{
  "models": [
    {
      "title": "Local Coder",
      "provider": "openai",
      "apiBase": "http://localhost:5000/v1",
      "model": "local-coder",
      "apiKey": "dummy"
    }
  ]
}
```

## Découverte automatique de nœuds -- Prise en charge du nom d'hôte `.local` (LAN domestique)

Lorsque vous exécutez plusieurs machines sur un LAN domestique (par exemple, Mac mini + Pi5 + machine GPU Windows), vous pouvez utiliser des noms d'hôte `.local` au lieu d'adresses IP dans `base_url`. De cette façon, **la configuration continue de fonctionner même si DHCP réattribue les adresses IP**. Aucune implémentation supplémentaire n'est requise du côté de yu_ai_manager -- `httpx` résout les noms automatiquement via le résolveur du système d'exploitation (Bonjour / Avahi / mDNSResponder).

```json
{
  "llm_router": {
    "enabled": true,
    "backends": [
      { "alias": "ollama-mac", "base_url": "http://mac-mini.local:11434/v1", "type": "ollama" },
      { "alias": "ollama-pi5", "base_url": "http://pi5.local:11434/v1",      "type": "ollama" },
      { "alias": "ollama-win", "base_url": "http://gpu-rig.local:11434/v1",  "type": "ollama" }
    ],
    "aliases": {
      "local-fast":  "ollama-mac/qwen2.5:7b",
      "local-coder": "ollama-pi5/qwen2.5-coder:32b",
      "local-big":   "ollama-win/llama3.3:70b"
    }
  }
}
```

Exemple: [`config.example.local-hostname.json`](../../../config.example.local-hostname.json)

### Pré-requis

| Système d'exploitation | Requis |
|---|---|
| macOS | Bonjour (intégré, aucune installation supplémentaire requise) |
| Linux | `avahi-daemon` (`sudo apt install avahi-daemon` / `sudo systemctl enable --now avahi-daemon`) |
| Windows 10/11 | mDNSResponder (Win10 1803 et versions ultérieures peuvent résoudre `.local` nativement. Si cela ne fonctionne pas, installez Bonjour Print Services) |

### Vérification

```bash
# Testez que la résolution fonctionne
python -c "import socket; print(socket.gethostbyname('mac-mini.local'))"
# → S'il retourne 192.168.x.x, c'est opérationnel
```

### Entre sous-réseaux / LAN d'entreprise / VPN

mDNS fonctionne via le multidiffusion L2, donc **il ne peut pas atteindre les routeurs, VPN ou VLAN isolés dans les réseaux d'entreprise**. Dans ces environnements, spécifiez les adresses IP directement comme avant:

```json
"backends": [
  { "alias": "remote-gpu", "base_url": "http://10.20.30.40:11434/v1", "type": "ollama" },
  { "alias": "tailscale-mac", "base_url": "http://100.x.x.x:11434/v1", "type": "ollama" }
]
```

Si vous avez besoin d'un réflecteur mDNS dans un environnement segmenté par VLAN, consultez votre administrateur LAN. yu_ai_manager ne fournit pas de réflecteur mDNS ou de proxy.

### Limitations connues

- **La résolution mDNS de Windows peut être occasionnellement lente** (~1 seconde): Il est recommandé de définir le `timeout` du backend sur 3 secondes ou plus
- **Le suffixe `.local` est obligatoire**: Utiliser simplement `mac-mini` retombera sur NetBIOS / DNS, donc écrivez toujours `mac-mini.local`
- **Ollama ne s'annonce pas via mDNS**: Seule la résolution de nom d'hôte est utilisée; le port (11434) doit être spécifié manuellement. Pour Ollama colocalisé avec yu, v4.71.0 ajoute un annonceur `_ollama._tcp.local.` du côté yu. Pour les nœuds Ollama purs (sans yu colocalisé), voir "Gestion des nœuds Ollama purs (sans yu colocalisé)" ci-dessous pour la politique

## Variables d'environnement

| Variable | Comportement |
|---|---|
| `TAGDB_DISABLE_LLM_ROUTER` | Définissez sur `1` pour désactiver entièrement le routeur |
| `TAGDB_DISABLE_LLM_ROUTER_REFRESH` | Définissez sur `1` pour désactiver la boucle d'actualisation de 5 minutes |
| `TAGDB_LLM_ROUTER_AUTH_MODE` | Remplacez par `none`/`loopback`/`api_key` |

## Documentation multilingue

Suivant les `docs/ reading rules` dans CLAUDE.md, les versions `en/zh-tw/zh-cn/ko` sont synchronisées en fonction de la source `ja/` (en tant que tâche séparée après la mise en œuvre; voir TODO.md).

## Découverte automatique de nœuds (Phase B -- v4.64.0 et ultérieures)

Les nœuds yu_ai_manager sur le même LAN se découvrent automatiquement via mDNS (`_yu-ai._tcp.local.`). Même sans rédiger manuellement les backends dans `config.json`, les nœuds découverts sont automatiquement enregistrés dans le `BackendCatalog` avec des alias `mdns-<prefix>`.

### Comment ça marche

1. Au démarrage, `core/mdns/` annonce `_yu-ai._tcp.local.`
2. Il s'abonne aux enregistrements TXT des autres nœuds et vérifie que les clés requises (version/node_id/llm_base_url) sont présentes
3. Pour les nœuds avec une version majeure correspondante, il envoie un HTTP GET à `http://<addr>:<web_port>/api/mdns/identity` pour confirmer que le produit/node_id/version correspondent
4. Les nœuds vérifiés sont enregistrés dans le routeur LLM comme `BackendInfo(alias="mdns-<node_id[:8]>")`
5. À partir de là, la boucle de sonde existante gère les actualisations périodiques

### Pré-requis

- Le répondeur mDNS du système d'exploitation doit être en cours d'exécution (macOS: Bonjour, Linux: Avahi, Windows: mDNSResponder)
- Les nœuds doivent être sur le même sous-réseau L2 (pour les scénarios entre routeurs / VPN, utilisez la configuration manuelle de la Phase A)
- UDP 5353 doit être autorisé via le pare-feu local
- **Ollama doit être exposé au LAN** -- Ollama se lie à `127.0.0.1:11434` par défaut, il est donc inaccessible depuis les autres nœuds du LAN. Définissez la variable d'environnement `OLLAMA_HOST=0.0.0.0:11434` avant de démarrer Ollama (macOS: `launchctl setenv OLLAMA_HOST "0.0.0.0:11434"`, Linux: unité systemd / `.bashrc`, Windows: variables d'environnement système). Si ceci n'est pas défini, yu_ai_manager détermine qu'il s'agit de localhost uniquement et n'annoncera pas `llm_base_url` (un avertissement apparaît dans le journal de démarrage)

### Détection automatique d'Ollama

S'il n'existe pas d'entrée localhost dans `llm_router.backends` dans `config.json`, yu_ai_manager recherche Ollama au démarrage dans l'ordre suivant:

1. `http://<LAN_IP>:11434/api/tags` -- Ollama accessible depuis le LAN
2. `http://localhost:11434/api/tags` -- Même si détecté, l'annonce LAN n'est pas effectuée (l'avertissement ci-dessus s'affiche)

Si une réponse 200 est retournée par l'adresse IP du LAN, elle est automatiquement incluse en tant que `llm_base_url` dans l'enregistrement TXT. Ceci est destiné à la participation sans configuration des nœuds Ollama colocalisés via mDNS. Les ports non standards (11435, etc.) ou lmstudio / llamacpp nécessitent toujours des entrées explicites dans `config.json`.

### Gestion des nœuds Ollama purs (sans yu colocalisé) (politique)

Les nœuds Ollama purs où `yu_ai_manager` ne s'exécute **pas** (par exemple, un Mac d'un membre de la famille qui n'a que Ollama installé, ou un conteneur Ollama sur un NAS) ne sont **pas couverts par la découverte automatique**. `Ollama` lui-même n'a pas de fonctionnalité qui annonce `_ollama._tcp.local.` officiellement, il n'y a donc structurellement aucun moyen de les détecter.

Pour utiliser ces nœuds à partir du routeur LLM, configurez-les **manuellement** via l'une des méthodes suivantes:

```json
{
  "llm_router": {
    "backends": [
      { "alias": "ollama-nas",    "base_url": "http://nas.local:11434/v1",     "type": "ollama" },
      { "alias": "ollama-family", "base_url": "http://192.168.1.42:11434/v1", "type": "ollama" }
    ]
  }
}
```

- Si votre environnement prend en charge les noms d'hôte `.local` (voir "Découverte automatique de nœuds -- Prise en charge du nom d'hôte `.local`" ci-dessus), privilégiez cela
- Sinon, codez en dur l'adresse IP fixe

#### Pourquoi la découverte automatique n'est pas tentée

Lors de la conception de ceci (2026-04-11), les trois options suivantes ont été comparées et l'option (c) orientation de configuration manuelle a été choisie:

| Option | Description | Décision |
|---|---|---|
| (a) Scanner tout le LAN `:11434` au démarrage | Sonde par force brute de tous les hôtes du sous-réseau | **Rejeté** -- charge réseau lourde, perturbateur sur LAN d'entreprise / grand, peut être confondu avec balayage de port, contredit la philosophie edge-first |
| (b) Daemon publicité Ollama externe | Expédition d'un annonceur léger fourni par yu qui s'exécute à côté de chaque hôte Ollama | **Rejeté** -- nécessite un processus résident supplémentaire, ce qui équivaut à installer uniquement `yu_ai_manager`. Contredit le point du "pur bare" |
| (c) Configuration manuelle du backend via IP fixe / `.local` | Entrées écrites à la main dans `config.json` | **Choisi** -- zéro implémentation supplémentaire, comportement explicite, évite d'entraîner les utilisateurs dans des analyses involontaires |

Si Ollama upstream annonce ultérieurement `_ollama._tcp.local.` officiellement, ou ajoute un mécanisme officiel de découverte de service, nous le réexaminerons en tant que Phase D à ce moment-là.

### Désactivation

Vous pouvez désactiver la découverte automatique dans les environnements où elle n'est pas nécessaire (isolation Docker, LAN d'entreprise, CI, etc.):

- Ajoutez `"mdns": {"enabled": false}` à `config.json`
- Ou définissez la variable d'environnement `YU_AI_MDNS_DISABLED=1`

### Comportements connus

- **Environnements multi-résidentiels (Wi-Fi + Ethernet)**: Avec le paramètre par défaut (`bind_address: null`), l'annonce se produit sur les deux interfaces et `PeerInfo.addresses` contient plusieurs adresses IP. Pour vous limiter à une seule interface, spécifiez `"bind_address": "192.168.x.y"`.
- **Collision d'alias**: Si un backend dans `config.json` utilise un alias au format `mdns-xxxxxxxx`, la configuration manuelle a la priorité et l'entrée découverte par mDNS est ignorée.
- **Entre sous-réseaux**: mDNS fonctionne uniquement dans le domaine de diffusion L2 par défaut. Pour le fonctionnement entre sous-réseaux, utilisez l'approche du nom d'hôte `.local` de la Phase A.
- **Sécurité**: mDNS lui-même n'a pas d'authentification. Il est conçu pour les environnements de confiance tels que les réseaux locaux domestiques. La désactivation est recommandée sur le Wi-Fi public ou les grands réseaux partagés. La vérification `/api/mdns/identity` empêche l'identification erronée accidentelle des nœuds ou le mélange de versions antérieures incompatibles.
