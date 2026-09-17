# Intégration Bridge

La fonctionnalité Bridge permet d'envoyer directement des prompts depuis YU AI Manager vers divers outils de génération d'images IA.

## Bridges disponibles

### SD WebUI Bridge
Intégration avec Stable Diffusion WebUI (Automatic1111 / Forge).
- Envoi et réception de prompts
- Transfert des paramètres de génération

### NAI Bridge
Intégration avec NovelAI.
- Conversion automatique de la syntaxe des prompts (SD ↔ NAI)
- Insertion automatique des tags de qualité

#### Vibe Transfer (potion NovelAI) et cache encode-vibe

Les modèles NAI V4+ nécessitent un pré-encodage des images de référence via `/ai/encode-vibe`
(**2 Anlas par appel**) avant leur utilisation dans les requêtes de génération.

Pour éviter de gaspiller des Anlas lors de générations répétées avec la même image, les
résultats d'encodage sont mis en cache localement :

```
data/nai_vibe_cache/<sha256>__<model>__<info_extracted>.bin
```

- **Clé** : SHA256 de l'image brute + nom du modèle + information extraite (pas de 0,01)
- **Taille maximale** : 500 Mo par défaut. Modifiable dans Settings > NAI Bridge > « Vibe encode cache (MB) » (0 = désactivé)
- **Éviction LRU** : les fichiers les plus anciens sont supprimés dans un thread d'arrière-plan quand la limite est dépassée

### ComfyUI Bridge
Intégration avec ComfyUI.
- Insertion de prompts dans les workflows
- Personnalisation du format de sortie

## Génération par lots

Les trois Bridges supportent la génération par lots dans le chemin de génération principal (sémantique compatible A1111).

### Batch count / Batch size

- **Batch count** — Nombre d'exécutions de génération séquentielles (axe temporel). Le client appelle l'API une fois par itération.
- **Batch size** — Nombre d'images générées en parallèle par appel API (axe VRAM). Non affiché dans NAI Bridge.
- Total d'images = Batch count × Batch size

Avec un seed fixe, le seed est incrémenté sous la forme `base + i` à chaque itération de la boucle (même comportement qu'A1111). Avec `-1` (aléatoire), un nouveau seed aléatoire est utilisé à chaque fois.

### Boutons d'arrêt

| Bridge | Exécution unique (count=1) | Loop (count>1) |
|---|---|---|
| NAI | Pas de bouton d'arrêt | Seulement « Arrêter après l'actuel » |
| SD WebUI | « Arrêter » (API cancel du serveur) | « Arrêter après l'actuel » + « Arrêter » |
| ComfyUI | « Arrêter » (API cancel du serveur) | « Arrêter après l'actuel » + « Arrêter » |

- **Arrêter (immédiat)** — Interrompt l'appel API en cours et arrête la boucle. Pour SD WebUI / ComfyUI, l'API cancel du serveur est également appelée.
- **Arrêter après l'actuel** — Laisse l'image en cours se terminer, puis ignore l'itération suivante.

NAI Bridge n'affiche pas de bouton d'arrêt pour la génération d'image unique car l'API NAI consomme des Anlas (crédits) au moment où elle accepte le fetch. Couper la connexion HTTP n'arrête pas la génération côté serveur et ne rembourse pas les crédits — un bouton d'arrêt ne ferait que prêter à confusion.

### Note sur la VRAM

Augmenter le Batch size accroît la consommation de VRAM du GPU serveur proportionnellement au nombre d'images. Avec SDXL et Batch size 4 ou plus, des erreurs OOM peuvent survenir ; commencez par 1 et augmentez progressivement.

## Préréglages de qualité

Le bouton « QP » dans la barre d'outils de chaque Bridge permet d'insérer des tags d'amélioration de qualité en un clic.

Préréglages intégrés :
- SD High Quality
- SD Realistic
- NAI Quality
- NAI Artistic
- Minimal

Des préréglages personnalisés peuvent également être créés.

## Préréglages de résolution

Un menu déroulant « Resolution Preset » et un bouton ⇄ Swap sont disponibles au-dessus des champs Width/Height dans SD WebUI Bridge et ComfyUI Bridge. Ils permettent de saisir des résolutions représentatives en un clic.

- **SD 1.5** — 5 variantes basées sur 512 pour les modèles SD1.5
- **SDXL Trained** — 9 variantes selon les buckets d'entraînement officiels SDXL (priorité qualité)
- **SDXL Cheat Sheet** — 12 variantes approchant les ratios cinéma/photo avec des multiples de 8 (priorité composition, source [Civitai](https://civitai.com/articles/2246/sdxl-image-size-cheat-sheet))

La sélection `Custom` conserve les valeurs W/H existantes. Si les valeurs W/H sont modifiées manuellement après avoir appliqué un préréglage, elles reviennent automatiquement à `Custom`. Le bouton ⇄ permet d'échanger Width et Height.

Les résolutions de la Cheat Sheet s'écartent des buckets officiels, ce qui peut légèrement affecter la composition selon le modèle.

> Dans ComfyUI Bridge, applicable uniquement en mode Simple. N'affecte pas les valeurs de nœuds en mode Raw JSON Workflow.

## Transfert entre Bridges

Les prompts peuvent être directement transférés entre Bridges. La syntaxe est automatiquement convertie entre SD et NAI.
