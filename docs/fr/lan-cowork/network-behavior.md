# Comportement réseau de LAN Cowork (ce qui se passe sur votre LAN)

> Cible : v4.538.0 et ultérieur du Rust standalone (`yu-server`). Pour les configurations
> hybrides (utilisant le backend Python), veuillez consulter « Différences avec la version Python »
> à la fin de ce document.

Cette page résume **« ce qui se passe sur le réseau lorsque vous activez LAN Cowork »**
en un seul document. Veuillez la consulter avant de modifier la configuration.

---

## Résumé

- **Rien n'est activé par défaut.** Rust standalone n'effectue ni écoute ni annonce sur le LAN,
  à moins que vous les activiez explicitement via la configuration décrite ci-après.
- Lorsque c'est activé, **votre nœud devient détectable par d'autres nœuds du même LAN**.
  C'est le comportement prévu par la conception.
- **La présence ou l'absence d'un PIN n'arrête pas l'annonce de découverte.** Pour plus de détails,
  consultez « Relation avec le PIN (point facilement mal compris) ».

---

## Ce qui se déclenche lorsqu'activé

| Action | Description |
|---|---|
| **Écoute UDP** | Établit une liaison sur `0.0.0.0:19850` (toutes les interfaces) |
| **Annonces périodiques** | Envoie un HELLO signé vers `255.255.255.255:19850` toutes les 10 secondes. Le contenu inclut l'ID du nœud, la clé publique, le port API, le nom d'hôte, etc. |
| **Enregistrement des autres nœuds** | Vérifie la signature du HELLO reçu et enregistre le nœud pair dans sa liste de pairs (TOFU) |
| **Acceptation des HTTP entrants** | Les points de terminaison pair listés ci-dessous commencent à répondre |
| **Diffusion locale** | Transmet les événements pair reçus au flux SSE (`/api/events/stream`) auquel les sessions connectées s'abonnent |
| **Nettoyage des expirations** | Nettoie la mémoire des demandes d'appairage expirées et des PIN en texte clair toutes les 60 secondes |

### Points de terminaison acceptés en entrant

| Point de terminaison | Authentification |
|---|---|
| `GET /ext/lan_cowork/api/peer/discover` | **Aucune session requise** (interrogation de la liste des pairs) |
| `GET /ext/lan_cowork/api/peer/status` | **Aucune session requise** (descripteur du nœud) |
| `POST /ext/lan_cowork/api/peer/register` | **Aucune session requise** (auto-enregistrement du pair ; le serveur valide la destination) |
| `POST /ext/lan_cowork/api/peer/pair/request` / `pair/verify` | **Aucune session requise** (initiation de l'appairage. Un pair non apparié ne peut pas posséder de session) |
| `POST /ext/lan_cowork/api/peer/token/renew` | Signature + nonce (Bearer non requis) |
| `POST /ext/lan_cowork/api/peer/event` / `heartbeat` | Signature + jeton Bearer |

« Aucune session requise » signifie **pas de session d'authentification requise**,
non pas « pas d'authentification du tout ». Puisqu'un pair non apparié ne peut pas avoir de session,
ces 5 routes sont les seules à être ouvertes en tant qu'exceptions.
Toutes les autres routes nécessitent une connexion comme d'habitude.

---

## Comment activer ou désactiver

Basculez via la section **`extensions`** de `config.json`.

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "enabled": true
    }
  }
}
```

- **L'absence de cette clé signifie « désactiver »** (Rust standalone).
- Un **redémarrage** est nécessaire pour que les modifications prennent effet.
- Pour des commutations temporaires, vous pouvez également spécifier via les options de lancement.
  L'ordre de priorité est **ligne de commande > `config.json` > variable d'environnement > défaut**.

| Méthode | Activation | Désactivation |
|---|---|---|
| Ligne de commande | `--native-daemon` | `--no-native-daemon` |
| Variable d'environnement | `YU_LAN_COWORK_NATIVE_DAEMON=1` | Identique `=0` |

> La variable d'environnement n'interprète que `1`, `true`, ou `yes` comme « activer ». `on` ou `Y`
> sont traités comme **désactiver**.

### Vérifier si c'est activé

```bash
curl -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5000/ext/lan_cowork/api/peer/status
```

| Réponse | Signification |
|---|---|
| `200` | Activé. La fonctionnalité pair fonctionne |
| `405` | **Désactivé** (la fonctionnalité n'est pas compilée dans ce binaire) |
| `503` | Activé mais non initialisé (clé du nœud non générée, ou l'initialisation interne a échoué) |

> **L'affichage de la liste des extensions dans l'interface ne peut pas être fiable.** Dans la liste
> des extensions, LAN Cowork peut afficher « actif », mais c'est basé sur les informations d'inclusion
> et **ne reflète pas si le daemon ci-dessus fonctionne réellement**. Fiez-vous plutôt à la réponse du point
> de terminaison ci-dessus ou à la ligne `native_daemon=...` du journal de démarrage.

---

## Relation avec le PIN (point facilement mal compris)

**L'idée que sans PIN, rien sur le LAN ne peut être affecté n'est pas exacte.**

- **Correct** : Utiliser `--lan` (écoute sur toutes les interfaces) nécessite un PIN, et le lancement
  s'arrête s'il est absent. Par défaut, l'écoute est sur `127.0.0.1`, donc **dans un lancement normal,
  la surface HTTP n'est pas accessible depuis le LAN**.
- **Avertissement 1** : Si vous spécifiez l'adresse IP du LAN directement avec `--host`,
  cette vérification obligatoire du PIN ne s'applique pas. De plus, sans PIN, la porte de connexion
  elle-même s'ouvre, donc **évitez d'exposer votre système au LAN sans PIN**.
- **Avertissement 2** : **L'annonce UDP est indépendante de la présence d'un PIN.** Une fois activée,
  même un nœud sans PIN annonce son existence sur le LAN toutes les 10 secondes. Le PIN ne limite que l'exposition HTTP.

En résumé, **le PIN limite l'exposition de la surface HTTP, mais n'arrête pas l'annonce de découverte.**

### En cas d'écoute uniquement sur loopback (v4.539.0 et versions ultérieures)

Si l'adresse d'écoute est uniquement loopback (la valeur par défaut `127.0.0.1`, qui s'applique aussi à la version de bureau),
**ce nœud ne s'annonce pas sur le LAN**. Les autres nœuds ne pourraient pas se connecter même s'il s'annonçait.
L'avertissement suivant est consigné une seule fois après le démarrage (c'est WARN et non INFO, il est donc visible par défaut).

```
LAN Cowork discovery inactive: server listens on loopback only; bind a LAN address or use --lan
```

Pour l'utiliser sur le LAN, liez une adresse LAN ou utilisez `--lan` (`--lan` exige un PIN).

> Avant v4.539.0, un écouteur uniquement sur loopback annonçait une IP LAN. Les pairs pouvaient le découvrir,
> mais ne pouvaient pas se connecter ; c'est pourquoi ce comportement a été modifié.

---

## À savoir avant d'activer

- **Même si vous désactivez, les informations pair enregistrées pendant qu'elle était active ne sont pas
  automatiquement supprimées.** De plus, **au premier lancement après activation**, un nettoyage des
  anciennes entrées pair est exécuté (les enregistrements inaccessibles depuis plus de 7 jours et les
  enregistrements non appairés depuis plus de 1 heure sont supprimés). Il est recommandé de sauvegarder
  `tags.db` avant le basculement.
- Les événements pair reçus sont transmis au flux SSE auquel les sessions connectées s'abonnent.
  **Le contenu provient de la saisie du nœud pair** (l'ID source est remplacé par le serveur par une
  valeur authentifiée).
- Dans les journaux, seul **le nombre, le type et l'ID source** sont enregistrés ; le contenu de
  l'événement n'est pas enregistré.
- Si vous souhaitez vérifier l'état opérationnel, activez le niveau de journal INFO
  (par exemple : `RUST_LOG=yu_server=info`). Avec les paramètres par défaut, aucune ligne indiquant
  la réception d'un événement pair ne sera générée.

---

## Différences avec la version Python

| | Backend Python hybride | Rust standalone |
|---|---|---|
| Défaut | **Activé** (activé si la clé est absente de `config.json`) | **Désactivé** (activation explicite requise) |
| Implémentation | Géré par l'extension Python | Géré par `yu-server` |

**Rust standalone est intentionnellement « désactivé par défaut ».** C'est pour éviter que la simple
mise à jour change le comportement réseau. Le comportement de la configuration hybride n'a pas changé
par rapport à avant.

> Dans la documentation passée, les paramètres d'activation étaient indiqués comme
> `{"lan_cowork": {"enabled": true}}` (niveau supérieur), mais **cette clé n'est lue par aucune
> implémentation.** La section `extensions` ci-dessus est la position correcte.
