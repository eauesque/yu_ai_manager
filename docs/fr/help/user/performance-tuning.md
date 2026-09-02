# Guide de Réglage des Performances

Guide de réglage pour utiliser confortablement YU AI Manager dans un environnement gérant plus de 100 000 fichiers. Même avec les paramètres par défaut, de nombreuses optimisations fonctionnent automatiquement, mais vous pouvez encore les améliorer en les ajustant selon votre environnement.

---

## 1. Matériel Recommandé

| Élément | Configuration minimale | Recommandée (plus de 100 000 fichiers) |
|------|---------|------------------------|
| CPU | 2 cœurs | 4 cœurs ou plus (la génération de miniatures est parallélisée) |
| RAM | 4 Go | 8 Go ou plus |
| Stockage | HDD | **SSD fortement recommandé** — directement lié à la vitesse de réponse de la base de données |
| Réseau | — | 1 Gbps ou plus en cas d'utilisation via LAN |

**Particulièrement important** : le fichier de base de données (`data/tags.db`) doit absolument être placé sur un SSD. Les fichiers image eux-mêmes peuvent être sur HDD sans problème, mais si la DB est sur HDD, la recherche et la navigation deviennent nettement plus lentes.

---

## 2. Optimisation du Premier Scan

### Division des Racines de Scan

Scanner un grand nombre de fichiers d'un seul coup prend du temps. Il est recommandé d'enregistrer plusieurs racines de scan distinctes dans Settings > Scan Roots et de scanner par étapes.

- Scanner d'abord les dossiers les plus utilisés
- Ajouter les autres dossiers à la file d'attente de scan (traitée automatiquement dans l'ordre)
- Les enregistrements en double d'un même dossier sont détectés et ignorés automatiquement

### Navigation Possible Pendant le Scan

Même pendant un scan, la recherche et l'affichage des miniatures fonctionnent normalement. En interne, une connexion en lecture seule à la base de données est utilisée, donc le processus d'écriture du scan ne bloque pas la navigation.

### Optimisation Automatique Après le Scan

À la fin du scan, les statistiques de la base de données sont mises à jour automatiquement (ANALYZE). Cela optimise le plan d'exécution des requêtes de recherche et accélère les recherches suivantes. Aucune opération particulière n'est requise.

---

## 3. Amélioration de la Vitesse de Navigation

### Cache Service Worker

Le Service Worker du navigateur met automatiquement en cache le contenu suivant :

| Type | Limite de cache | Effet |
|------|-------------|------|
| Miniatures | 5 000 éléments | Affichage de la grille instantané à partir de la 2e fois |
| Prévisualisation (1200px) | 200 éléments | Accélération de l'affichage modal |
| Image taille réelle | 50 éléments | Réaffichage instantané des images récemment vues |

Le Service Worker est géré automatiquement par le navigateur, aucune configuration particulière n'est nécessaire. Pour vider le cache, vous pouvez utiliser les outils de développement du navigateur > Application > Storage.

### Activation du Défilement Virtuel

Lors de l'affichage de milliers de résultats de recherche, l'activation du défilement virtuel améliore considérablement les performances de rendu.

**Procédure d'activation** : Settings > Appearance > « Virtual Scroll » sur ON

Le défilement virtuel ne rend dans le DOM que les cartes visibles à l'écran, réduisant considérablement l'utilisation mémoire et la charge de rendu. Fortement recommandé pour les bibliothèques de dizaines de milliers d'éléments.

### Miniatures WebP

Les miniatures sont générées au format WebP (30-40% plus petites que JPEG). Cela réduit le volume de transfert, particulièrement efficace pour les accès via LAN. Aucune configuration n'est nécessaire, cela s'applique automatiquement.

---

## 4. Performances de Recherche

### Effet des Index

Des index optimisés pour les principaux modèles de recherche sont automatiquement créés dans la base de données. Le tri par date, le filtrage par tag, la recherche par chemin, etc., fonctionnent rapidement.

**Références** :
- Recherche sans filtre : réponse en moins de 50ms même à l'échelle de 280 000 éléments
- Recherche avec filtre de tag : moins de 100ms
- Recherche de chemin (FTS5) : moins de 50ms

### Recherche en Texte Intégral FTS5 vs Recherche LIKE

L'index FTS5 (Full-Text Search) est automatiquement utilisé pour la recherche de chemin. Il est 20-100 fois plus rapide que la recherche LIKE classique (`%keyword%`).

Si FTS5 n'est pas disponible (lors d'une mise à niveau depuis une ancienne DB, etc.), un retour automatique à la recherche LIKE est effectué. Un seul scan suffit pour construire l'index FTS5.

**Remarque sur la recherche en japonais** : les recherches contenant des kanji, hiragana ou katakana peuvent utiliser en interne le repli LIKE. C'est dû à une limitation du tokenizer FTS5 de SQLite et c'est un comportement normal.

---

## 5. Optimisation de la Lecture Vidéo

### Cache Faststart

Pour accélérer la lecture des fichiers MP4/MOV, le traitement faststart est appliqué automatiquement. La lecture en streaming des vidéos déjà traitées avec faststart démarre instantanément.

| Élément | Valeur |
|------|-----|
| Emplacement du cache | `cache/faststart/` |
| Limite de capacité | 4 Go (gestion LRU automatique) |
| Limite par fichier | 500 Mo |
| Cible | MP4, MOV (WebM ignoré car non nécessaire) |

**Référence d'amélioration ressentie** :

| Taille du fichier | Sans faststart | Avec faststart |
|--------------|---------------|---------------|
| 5-50 Mo | 2-10 secondes d'attente | Démarrage lecture en ~200ms |
| 50-200 Mo | 10-60 secondes d'attente | Démarrage lecture en ~500ms |
| 200-500 Mo | Plusieurs minutes d'attente | Démarrage lecture en ~1 seconde |

### Vérification de FFmpeg

FFmpeg est nécessaire pour le traitement faststart. S'il n'est pas installé, les vidéos sont lues après téléchargement complet.

```bash
ffmpeg -version
```

Si FFmpeg n'est pas trouvé dans le PATH, installez-le depuis le [site officiel](https://ffmpeg.org/download.html).

---

## 6. Gestion de l'Utilisation Mémoire

### SQLite mmap

Pour les grandes bases de données (plus de 100 000 fichiers), le mmap de SQLite (E/S mappée en mémoire) est automatiquement configuré à 1 Go. Cela accélère les requêtes de lecture en exploitant le cache de pages de l'OS.

**Environnements avec 4 Go de RAM ou moins** : mmap peut peser sur la mémoire. Dans ce cas, surveillez la mémoire libre du système et si des swaps fréquents se produisent, fermez d'autres applications.

### Gestion des Onglets du Navigateur

YU AI Manager communique en temps réel avec chaque onglet via SSE (Server-Sent Events).

- Maximum 10 connexions SSE simultanées par IP
- Fermer les onglets inutiles libère des ressources de connexion
- Ouvrir de nombreux onglets augmente aussi l'utilisation mémoire du navigateur

**Recommandé** : limiter à 3-4 onglets ouverts simultanément.

---

## 7. Dépannage — Checklist Lorsque Cela Semble « Lent »

### Vérifications de Base

- [ ] **Utilisez-vous un SSD ?** : si `data/tags.db` est sur HDD, toutes les opérations sont lentes
- [ ] **FFmpeg est-il installé ?** : indispensable pour l'accélération de la lecture vidéo
- [ ] **Nombre d'onglets du navigateur** : vérifiez que pas plus de 5 sont ouverts

### La Navigation est Lente

- [ ] **Activer le défilement virtuel** : Settings > Appearance > Virtual Scroll
- [ ] **Ne pas vider le cache du navigateur** : le cache du Service Worker est actif
- [ ] **Vérifier si un scan est en cours** : utilisable normalement pendant un scan, mais la génération initiale de miniatures prend du temps

### La Recherche est Lente

- [ ] **Terminer le scan** : ANALYZE est exécuté à la fin du scan et optimise la recherche
- [ ] **Plus de 100 000 résultats de recherche** : ajoutez des filtres (tag, date, chemin, etc.) pour affiner les résultats

### La Lecture Vidéo est Lente

- [ ] **Vérifier la présence de FFmpeg** : avec `ffmpeg -version`
- [ ] **Capacité du cache faststart** : vérifier que le dossier `cache/faststart/` ne dépasse pas 4 Go (gestion auto mais vérifiable)
- [ ] **Taille du fichier** : les vidéos de plus de 500 Mo ne sont pas mises en cache faststart. Elles sont diffusées via Range, mais la première fois est un peu plus lente

### Le Serveur Entier est Lourd

- [ ] **Nombre d'accès simultanés** : les connexions SSE ne dépassent pas 10 par IP
- [ ] **Téléversement en cours** : pas d'envoi d'un fichier proche de la limite de 100 Mo d'upload
- [ ] **Settings > Onglet Logs** : vérifier les erreurs et avertissements dans les logs serveur

---

## 8. Références d'Indicateurs de Performance

Référence des temps de réponse dans un environnement correctement optimisé.

| Opération | Échelle 280 000 fichiers | Échelle 100 000 fichiers |
|------|-----------------|-----------------|
| Affichage grille (première fois) | 200-500ms | 100-300ms |
| Affichage grille (avec cache) | moins de 50ms | moins de 50ms |
| Recherche par tag | moins de 100ms | moins de 50ms |
| Recherche de chemin (FTS5) | moins de 50ms | moins de 30ms |
| Miniature (cache hit) | moins de 5ms | moins de 5ms |
| Démarrage lecture vidéo (faststart fait) | 200ms | 200ms |

Si ces valeurs sont largement dépassées, consultez la checklist ci-dessus.

---

## Mode rapide (serveur Rust)

Sur les environnements pris en charge, le démarrage bascule automatiquement sur le serveur Rust (`yu-server`).

Dans Paramètres -> « Serveur » -> « Mode rapide », on choisit **le mode d'obtention** :

- **Télécharger le binaire publié** (par défaut) -- ne compile jamais
- **Compiler sur cette machine** -- ne télécharge jamais
- **Télécharger, et compiler en cas d'échec**

La compilation nécessite 8 Go d'espace libre et sollicite fortement le processeur et la mémoire. **Sur les machines à faible mémoire (un Raspberry Pi par exemple), elle peut épuiser la swap et faire planter tout le système.** Toutes les fonctions restent utilisables pendant la compilation. Compiler sous Windows demande en plus les outils de compilation Visual Studio (l'éditeur de liens).

La progression s'affiche sur le même écran : temps écoulé, dernière ligne de cargo, réussite ou échec, et si la compilation s'est arrêtée en route. Le journal brut se trouve dans `bin/fast-mode-build.log`.

Lorsque le mode rapide est refusé à cause de l'état de cette copie (bundle web périmé, extension hors de la liste fournie), récupérer un binaire n'y changerait rien : ni téléchargement ni compilation ne sont tentés. Cette raison y est également affichée.
