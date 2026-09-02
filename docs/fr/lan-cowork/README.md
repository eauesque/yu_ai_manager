# LAN Cowork

> Version cible : v4.55.0 et ultérieures (authentification PIN disponible à partir de v4.92.0)

## Qu'est-ce que LAN Cowork ?

LAN Cowork est une fonctionnalité d'extension qui permet la coordination entre plusieurs nœuds yu_ai_manager sur un réseau.  
Chaque machine fonctionne indépendamment, tout en permettant une répartition des tâches de traitement lourd ou une gestion collective sous forme de Fleet.

```
┌──────────────┐     Découverte mDNS  ┌──────────────┐
│  Windows PC  │◄────────────────────►│   Mac Mini   │
│ (GPU activé) │   Appairage PIN     │ (Contrôle)   │
│              │◄────────────────────►│              │
│  Inférence   │                     │  Gestion de  │
│ distribuée   │                     │    Fleet     │
│(marqueur etc)│                     │              │
└──────────────┘                     └──────────────┘
        ▲                                    ▲
        └────────────────────────────────────┘
                      ▼
              ┌──────────────┐
              │ Raspberry Pi │
              │ (Hailo NPU)  │
              └──────────────┘
```

---

## Aperçu des fonctionnalités

| Fonctionnalité | Description |
|---|---|
| **Découverte automatique mDNS** | Découvrir automatiquement les nœuds sur le même LAN sans configuration |
| **Appairage PIN** | Authentification PIN approuvée par l'administrateur pour l'émission de jetons entre pairs |
| **Inférence distribuée** | Traitement parallèle des marqueurs, CLIP, YOLO et Whisper sur plusieurs nœuds |
| **Distribution de génération** | Déléguer les tâches SD WebUI / ComfyUI aux nœuds LAN |
| **Gestion de Fleet** | Gérer centralement les journaux et les mises à jour de version sur tous les nœuds |
| **Relais d'événements de pairs** | Transmettre les événements d'autres nœuds à votre propre SSE |
| **Routage LLM** | Enregistrer automatiquement les pairs découverts dans LLM Router |

---

## Étapes de configuration

### 1. Activation

Ajouter à `config.json` :

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "enabled": true,
      "peer_name": "my-desktop"
    }
  }
}
```

> **Remarque** : Cette page indiquait auparavant la clé d’activation au niveau supérieur sous la forme `{"lan_cowork": {...}}`, mais aucune implémentation ne lit une clé à cet emplacement. La section `extensions` ci-dessus est le bon emplacement.

> **Le comportement par défaut dépend du backend :** le backend Python (hybride) considère une clé absente comme **activée**, tandis que le serveur Rust autonome est **désactivé** sans activation explicite. Pour savoir ce qui se passe réellement sur le réseau une fois activé, consultez [Comportement réseau](network-behavior.md).

Après redémarrage :
- Écouter les autres nœuds sur UDP 19850
- Commencer l'annonce de _yu-ai._tcp.local. via mDNS

### 2. Appairer les nœuds

Pour vous connecter du Nœud A au Nœud B :

1. **Interface Web du Nœud A** → `Paramètres` → `LAN Cowork` → Ajouter l'URL du Nœud B
2. Le Nœud A envoie `POST /api/lan/pair/request`
3. **Interface Web du Nœud B** → `/lan-cowork/peers` → Approuver dans l'onglet "Approbation en attente"
4. Code PIN à 6 chiffres est envoyé au Nœud A (via SSE)
5. Le Nœud A saisit le PIN → Obtenir le jeton Bearer (valide 30 jours)

> **Remarque** : L'appairage est unidirectionnel. Effectuez à la fois A→B et B→A.

Voir [Authentification PIN entre pairs et Appairage de jeton](peer-auth.md) pour plus de détails.

### 3. Vérifier le fonctionnement

```bash
# Liste des pairs découverts (depuis Nœud A)
curl http://localhost:5000/api/mdns/peers

# Pairs reconnus par LAN Cowork
curl http://localhost:5000/api/lan/peers
```

---

## Configuration spécifique à chaque fonctionnalité

### Inférence distribuée

L'inférence distribuée devient disponible automatiquement après l'appairage.

- `Paramètres` → `LAN Cowork` → Activer les types d'inférence (marqueur/CLIP/YOLO/Whisper) pour chaque nœud
- Ou configurer individuellement via la matrice sur la page `/mesh-inference`

Détails : [Configuration de l'inférence distribuée](../mesh-inference/setup.md)

### Gestion de Fleet

Configurez un nœud "chef" pour gérer les autres nœuds :

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "fleet": {
        "chief": true,
        "allow_remote_update": true,
        "allow_update_from": [
          "<paired peer_id>"
        ]
      }
    }
  }
}
```

Détails : [Gestion de Fleet](../features/fleet-admin.md)

### Distribution de génération (Délégation de tâches SD / ComfyUI)

Distribuez automatiquement les tâches de génération aux nœuds équipés de GPU. Disponible via l'enregistrement du backend du fichier de configuration ou la découverte automatique mDNS.  
Si le Nœud B exécute SD WebUI / ComfyUI, il devient disponible immédiatement après la configuration.

---

## Exigences du réseau

| Port / Protocole | Objectif | Requis |
|---|---|---|
| UDP 5353 | mDNS (découverte de nœuds) | Même LAN L2 uniquement |
| UDP 19850 | Découverte LAN Cowork | Même LAN L2 uniquement |
| TCP 5000 (par défaut) | API, appairage, inférence | Entre pairs |

- mDNS ne fonctionne pas à travers les routeurs ou les VPN (utilisez l'adresse IP fixe ou le nom d'hôte `.local`)
- Assurez-vous que UDP 5353 et TCP 5000 sont ouverts sur le LAN dans votre pare-feu

---

## Index de documentation

| Document | Contenu |
|---|---|
| [Authentification PIN entre pairs](peer-auth.md) | Flux d'appairage, gestion des jetons, configuration de sécurité |
| [Configuration de l'inférence distribuée](../mesh-inference/setup.md) | Étapes pour paralléliser l'inférence sur plusieurs nœuds |
| [Matrice d'inférence distribuée](../mesh-inference/toggle.md) | Activer/désactiver par pair et par type via l'interface Web |
| [Architecture d'inférence distribuée](../mesh-inference/overview.md) | Conception interne, vol de travail, persistance |
| [Gestion de Fleet](../features/fleet-admin.md) | Gestion centralisée des journaux distants et des mises à jour de version |
| [API Pair mDNS](../api/mdns-peers.md) | Détails des points de terminaison `/api/mdns/*` |

---

## Sécurité

- mDNS n'a pas d'authentification. **Utilisez uniquement sur les réseaux domestiques ou de confiance**
- Sur les Wi-Fi publics ou les LAN partagés, désactivez avec `"mdns": {"enabled": false}`
- La communication entre pairs est protégée par les jetons Bearer issus du jumelage PIN (stockés en tant que hash scrypt)
- `ip_check_mode: strict` autorise uniquement l'adresse IP à partir de laquelle le jeton a été émis (par défaut)
