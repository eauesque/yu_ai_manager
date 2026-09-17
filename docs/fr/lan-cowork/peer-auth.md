# Authentification PIN entre Pairs et Appairage de Tokens

**Version d'implémentation** : 4.92.0
**Fichiers associés** : `extensions/builtin_lan_cowork/`, `core/lan_cowork_core/`

---

## Vue d'ensemble

Avant v4.92, dans les communications entre pairs sur le LAN, l'identification du correspondant se faisait uniquement via l'en-tête `X-Peer-Id`. Cet en-tête pouvant être falsifié par n'importe qui sur le LAN, la sécurité était insuffisante.

À partir de v4.92, migration vers une méthode d'**appairage de tokens basée sur l'approbation par PIN**.

- À la première connexion, envoi d'une « demande d'appairage »
- L'administrateur du correspondant approuve dans l'écran d'administration et émet un PIN à 6 chiffres
- La saisie du PIN émet un token Bearer (valable 30 jours)
- Les communications ultérieures s'authentifient avec `Authorization: Bearer <token>`

L'ancienne méthode d'en-tête `X-Peer-Id` peut être conservée pour la compatibilité via les paramètres, mais les opérations DELETE exigent toujours la nouvelle authentification.

---

## Flux d'Appairage

```
[Pair source A]                        [Pair destination B]
       |                                      |
       |--- POST /api/lan/pair/request ------->|
       |    (peer_id, display_name, public_key)|
       |                                      |
       |                              L'administrateur vérifie/approuve dans /lan-cowork/peers
       |                                      |
       |<--- SSE: peer_pairing.pin_ready ------|
       |    (PIN 6 chiffres, expire en 5 min)  |
       |                                      |
       |--- POST /api/lan/pair/verify -------->|
       |    (peer_id, pin)                     |
       |                                      |
       |<--- 200 OK: { token, expires_at } ----|
       |    (Token Bearer, valide 30 jours)    |
       |                                      |
       |--- Ensuite Authorization: Bearer <token> |
```

### Détails de chaque étape

| Étape | Endpoint | Description |
|----------|---------------|------|
| 1. Envoi de la requête | `POST /api/lan/pair/request` | Envoie ID pair, nom d'affichage, clé publique |
| 2. Attente d'approbation | — | L'administrateur vérifie dans `/lan-cowork/peers` |
| 3. Émission du PIN | — | L'administrateur appuie sur Approuver, génère un PIN à 6 chiffres (valide 5 min) |
| 4. Vérification du PIN | `POST /api/lan/pair/verify` | Envoie le PIN et reçoit le token Bearer |
| 5. Communication authentifiée | — | Ajoute l'en-tête `Authorization: Bearer <token>` |

---

## Écran d'Administration (`/lan-cowork/peers`)

### Requêtes en attente d'approbation

Quand une nouvelle requête d'appairage arrive d'un pair, elle apparaît dans l'onglet « En attente d'approbation » de l'écran d'administration.

- **Approuver** : génère un PIN et notifie via SSE le pair à l'origine de la requête
- **Refuser** : supprime la requête. Un 403 est renvoyé au pair source

### Liste des pairs connectés

Liste les pairs appairés avec la date d'expiration de chaque token.

| Colonne | Contenu |
|----|------|
| Nom d'affichage | Nom du pair |
| Adresse IP | Dernière IP source confirmée |
| Expiration | Date d'expiration du token Bearer (30 jours) |
| Dernière connexion | Heure du dernier heartbeat |
| Action | Bouton de révocation de token |

### Révocation de token

Le bouton « Révoquer » invalide immédiatement le token Bearer du pair ciblé. Au prochain échange, un 401 est renvoyé et le pair tente automatiquement un ré-appairage.

---

## Paramètres

Les paramètres sont modifiables dans la section `extensions` de `config.json`, sous l'entrée `builtin-lan-cowork`, ou dans l'onglet « Collaboration LAN » de l'écran de configuration.

### `ip_check_mode`

Spécifie la méthode de vérification de l'IP source.

| Valeur | Comportement |
|----|------|
| `strict` | Autorise uniquement une correspondance exacte avec l'IP au moment de l'émission du token (par défaut) |
| `cidr` | Autorise si dans la plage CIDR spécifiée par `allowed_cidr` |
| `rfc1918` | Autorise toutes les IP privées (192.168.x.x / 10.x.x.x / 172.16-31.x.x) |

### `allow_legacy_auth`

Indique si la compatibilité avec l'ancienne authentification par en-tête `X-Peer-Id` est maintenue.

- `true` : certaines opérations sont autorisées avec seulement l'en-tête `X-Peer-Id` (par défaut : `true`)
- `false` : refuse toute connexion sans token Bearer

> **Remarque** : les opérations utilisant la méthode `DELETE` (arrêt de scan, suppression forcée, etc.) exigent toujours un token Bearer, quel que soit le paramètre `allow_legacy_auth`.

### `protect_heartbeat`

Indique si l'endpoint heartbeat (`/api/lan/heartbeat`) requiert aussi une authentification.

- `true` : le heartbeat aussi requiert un token Bearer
- `false` : le heartbeat passe sans authentification (par défaut : `false`)

Le heartbeat étant envoyé fréquemment, le mettre à `false` évite le retard de détection d'expiration de token.

### `protect_events`

Indique si le flux d'événements SSE (`/api/events/`) requiert aussi une authentification.

- `true` : la connexion SSE aussi requiert un token Bearer
- `false` : SSE passe sans authentification (par défaut : `false`)

---

## Notes de Sécurité

### Hachage des tokens

Les tokens Bearer émis **ne sont pas stockés en clair** dans la base de données. Ils sont stockés hachés via scrypt (N=16384, r=8, p=1). Même si la DB fuit, le token original ne peut pas être récupéré.

### Masquage dans les logs

- L'en-tête `Authorization: Bearer <token>` est automatiquement remplacé par `Bearer [REDACTED]` dans les logs
- Les codes PIN ne restent pas dans les logs non plus

### Limite de Taux

Pour prévenir les attaques DoS et brute force, les limites de taux suivantes s'appliquent.

| Endpoint | Limite |
|---------------|------|
| `POST /api/lan/pair/request` | 10/minute/IP |
| `POST /api/lan/pair/verify` | 30/minute/IP |

Le PIN expire automatiquement en 5 minutes, et une seule vérification par requête est possible.

---

## Dépannage

### La requête d'appairage n'arrive pas

- Vérifiez que l'URL du pair correspondant est correctement configurée
- Vérifiez que le port n'est pas bloqué par le pare-feu
- Vérifiez dans les logs du pair correspondant la réception de `pair/request`

### Le PIN a expiré

La durée de validité du PIN est de 5 minutes. En cas d'expiration, appuyer à nouveau sur « Approuver » dans l'écran d'administration émet un nouveau PIN.

### Le token ne fonctionne plus soudainement

Les causes possibles sont :

1. L'administrateur a révoqué le token depuis l'écran d'administration
2. La durée de 30 jours a expiré
3. En `ip_check_mode: strict`, l'adresse IP a changé

Effectuez un ré-appairage.

### Plus de connexion après avoir mis `allow_legacy_auth` à `false`

Si des pairs existants sont restés sur l'ancienne méthode d'authentification, ils reçoivent tous un 401. Effectuez le ré-appairage de chaque pair avant de passer à `allow_legacy_auth: false`.
