# Guide de Configuration de l'Inférence Distribuée

> Version cible : v4.67.0 et ultérieure

## Qu'est-ce que l'Inférence Distribuée ?

Une fonctionnalité où plusieurs nœuds yu_ai_manager collaborent pour **paralléliser et distribuer** le traitement de l'inférence tel que l'étiquetage, CLIP, YOLO et la reconnaissance vocale. Vous pouvez partager les analyses de fichiers volumineux sur plusieurs machines ou déléguer l'étiquetage à un Pi5 avec Hailo NPU.

```
┌──────────────┐   Lots d'Images  ┌──────────────┐
│   Local      │ ──────────────► │  Pi5 (Hailo) │  tagger × 200 images
│   (Analyse)  │ ──────────────► │Machine GPU   │  tagger × 300 images
│              │ ──────────────► │    Local     │  tagger × 100 images
└──────────────┘   Travail       └──────────────┘
                  Partagé
```

---

## Conditions Préalables

Les conditions suivantes doivent être remplies sur chaque nœud :

1. yu_ai_manager fonctionne
2. **L'extension LAN Cowork est activée** (`"extensions": {"builtin-lan-cowork": {"enabled": true}}`)
3. Les nœuds sont **appairés les uns avec les autres** ([Guide d'Authentification des Pairs](../lan-cowork/peer-auth.md))
4. Les moteurs d'inférence à utiliser sont configurés sur chaque nœud (ONNX / Hailo / Whisper, etc.)

---

## Étapes de Configuration

### Étape 1 : Activer LAN Cowork sur Chaque Nœud

Dans `config.json` sur tous les nœuds :

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "enabled": true
    }
  }
}
```

Après le redémarrage, les nœuds se découvriront automatiquement via mDNS.

### Étape 2 : Terminer l'Appairage

Effectuez l'appairage entre toutes les paires de nœuds (bidirectionnel).
Détails : [Authentification par PIN et Appairage des Jetons](../lan-cowork/peer-auth.md)

### Étape 3 : Vérifier la Matrice d'Inférence Distribuée

Ouvrez `/mesh-inference` sur n'importe quel nœud.

Les nœuds appairés apparaissent sous forme de lignes, les types d'inférence sous forme de colonnes :

| Nœud | tagger | clip | yolo | whisper |
|---|---|---|---|---|
| Local | ☑ Activé | ☑ Activé | ☑ Activé | ☑ Activé |
| pi5-hailo | ☑ Activé | ☑ Activé | — Non disponible | — Non disponible |
| gpu-win | ☑ Activé | ☑ Activé | ☑ Activé | ☑ Activé |

- **☑ Activé** : Utiliser ce nœud pour l'inférence
- **☐ Désactivé** : Ignorer (peut être basculé manuellement)
- **—** : Ce nœud n'a pas le moteur d'inférence cible (ne peut pas être contrôlé)

### Étape 4 : Vérifier le Fonctionnement

Exécutez un lot d'étiquetage et confirmez dans les journaux que plusieurs nœuds sont utilisés :

```
[mesh-inference] dispatching tagger: 600 items to 3 peers
[mesh-inference] pi5-hailo: processed 200, errors 0
[mesh-inference] gpu-win:   processed 300, errors 0
[mesh-inference] local:     processed 100, errors 0
```

---

## Exigences par Type d'Inférence

| Type | Moteur Requis | Description |
|---|---|---|
| `tagger` | ONNX (WD14, etc.) ou Hailo NPU | Étiquetage de style Danbooru pour les images |
| `clip` | ONNX CLIP ou Hailo | Vecteurs d'incorporation sémantique pour les images (pour la recherche sémantique) |
| `yolo` | ONNX YOLO | Détection d'objets dans les images |
| `whisper` | faster-whisper ou à distance | Transcription de la parole en texte pour audio/vidéo |

Les nœuds sans moteur configuré afficheront « — » pour ce type et ne seront pas acheminés pour ce type.

---

## Exemples de Conception de Rôles

### Exemple 1 : Dédier Pi5 + Hailo NPU pour l'Étiquetage

Allouez Pi5 exclusivement pour l'étiquetage afin de réduire la charge sur les autres nœuds.

Configuration de la matrice :
- Pi5 : tagger ☑, autres ☐
- Local : clip ☑, yolo ☑, whisper ☑, tagger ☐ (déléguer à Pi5)

### Exemple 2 : Analyse en Masse Rapide

Activez tagger sur la machine GPU et la machine locale, partageant automatiquement les fichiers via le travail partagé. Aucune division manuelle requise.

### Exemple 3 : Mode Local Uniquement (Temporaire)

Cliquez sur le bouton « Mode Local Uniquement » dans `/mesh-inference` pour désactiver tous les pairs distants à la fois. Utile en cas de déconnexion réseau.

---

## Dépannage

### Le Pair N'Apparaît Pas dans la Matrice

1. Vérifiez que le pair est reconnu avec `/api/lan/peers`
2. Confirmez que l'appairage est complet ([peer-auth.md](../lan-cowork/peer-auth.md))
3. Vérifiez que LAN Cowork est activé sur le nœud distant

### L'Acheminement vers un Nœud Spécifique Ne Fonctionne Pas

- Vérifiez que le type cible pour ce nœud affiche ☑ dans la matrice
- Vérifiez que la réponse de `/api/lan/peers` affiche `status: "online"` pour ce nœud
- Vérifiez que le battement du nœud distant est reçu (recherchez `heartbeat` dans les journaux)

### Tout Est Traité Localement

Si tous les pairs distants sont hors ligne ou désactivés, une récupération locale automatique se produit.
Ceci est un fonctionnement normal (pas une erreur).

### Erreur `no_enabled_peers`

Ce type est désactivé sur tous les nœuds.
Activez au moins 1 nœud pour ce type dans la matrice.

---

## Documentation Connexe

- [Architecture de l'Inférence Distribuée](overview.md) — Conception interne du travail partagé et DisableAwareStrategy
- [Matrice d'Inférence Distribuée](toggle.md) — Détails du fonctionnement de l'interface Web
- [Aperçu de LAN Cowork](../lan-cowork/README.md) — Configuration générale de LAN Cowork
- [Authentification par PIN des Pairs](../lan-cowork/peer-auth.md) — Procédure d'appairage
