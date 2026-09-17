# Guide de l’UI des profils WD-Tagger

Ce document explique l’**interface de gestion des profils** WD-Tagger (ajoutée en v4.197.0+).

## 1. Aperçu

- Un **profil** regroupe les réglages WD-Tagger : fichiers du modèle, définition des tags, seuils et prétraitement.
- Ouvrir : page Tools → section **WD-Tagger** → `Gérer les profils...`.
- Dans la fenêtre modale, on bascule entre **Liste (List)** et **Formulaire (Form)**.

## 2. Vue liste (List)

### 2.1 Badges (Builtin / User)

- `builtin` : profils intégrés (lecture seule)
- `user` : profils utilisateur (création/modification/suppression possibles)
- `↻` : ce profil **remplace** un profil intégré avec le même `id`

### 2.2 Filtre (All / User / Builtin)

Boutons en haut :

- `Tous`
- `Utilisateur`
- `Intégrés`

### 2.3 Boutons (actions)

Actions par ligne :

- `Dupliquer` : copie le profil et ouvre le formulaire (pour personnaliser un profil intégré)
- `Modifier` : modifier un profil utilisateur (intégrés non modifiables)
- `Supprimer` : supprimer un profil utilisateur (intégrés non supprimables)
- `Exporter` : télécharger le profil en `.json`
- `Tester (téléchargement à blanc)` : vérifier sans télécharger réellement que les fichiers sont récupérables depuis HuggingFace

En haut à droite :

- `+ Nouveau` : créer un profil vide
- `Importer` : créer un profil depuis un JSON (upload / collage)

## 3. Vue formulaire (Form)

Le formulaire comporte 5 sections en accordéon.

### 3.1 Metadata

- `id` : identifiant (ne peut pas être modifié ensuite)
- `Nom d’affichage` : nom affiché dans la liste
- `profile_version` : version du schéma (souvent inutile de changer)

### 3.2 Model & Files

- `model_id` : id du modèle HuggingFace (ex. `SmilingWolf/wd-swinv2-tagger-v3`)
- `adapter_family`, `backend`, `hf_subdir` : uniquement si nécessaire
- `Fichiers` :
  - `name` : nom du fichier (ex. `model.onnx`)
  - `Requis` : traité comme obligatoire lors du test
  - `size_hint_mb` : optionnel
  - `+ Ajouter un fichier` / `Retirer` : ajouter/retirer des lignes

### 3.3 Tag source

Source des définitions de tags.

- `csv` : fichier(file), séparateur(delimiter), colonne du nom(name_col), colonne catégorie(category_col), table(category_map)
- `json_list` : fichier(file), schéma(schema)
- `json_dict` : fichier(file), correspondance(mapping)
- `composite` : combinaison des sources(sources)

### 3.4 Threshold source

Source des seuils.

- `global_per_category` : définir les seuils par catégorie dans l’UI
- `per_tag` : fichier + repli
  - fichier(file)
  - mode de repli(fallback.mode) : `global` / `category_default`
  - valeur de repli(fallback.value)

### 3.5 Preprocess & Categories

- Prétraitement(`preprocess_spec`) : `input_size`, `dtype`, `layout`, `channel_order`, `resize_strategy` (`letterbox` / `longest_side_pad` / `stretch`), `scale`, `mean`, `std`
- Catégories :
  - `Catégories prises en charge`
  - `categories_mode` : `from_tag_source` / `all_general`

## 4. Import / Export

### 4.1 Importer

`Importer` propose deux onglets :

- Téléverser un JSON : envoyer un fichier `.json`
- Coller le JSON : coller le JSON dans la zone de texte

Après import, le formulaire s’ouvre. Vérifiez/modifiez puis `Enregistrer`.

### 4.2 Exporter

Dans la liste, `Exporter` télécharge le profil en JSON.

## 5. Tester (téléchargement à blanc)

- Vérifie si les fichiers listés dans `files` sont récupérables depuis **HuggingFace**.
- En succès, un bandeau peut afficher `Téléchargement OK : {n} fichiers ({total} MB)`.
- En échec, un bandeau indique la cause (section suivante).

## 6. Erreurs fréquentes (bref)

- `id_conflict` : un profil utilisateur avec le même `id` existe déjà
- `id_immutable` : `id` est immuable (renommer via Dupliquer → Supprimer)
- `in_use` : impossible de supprimer car le profil est actif
- `validation_failed` : validation échouée (`{detail}` contient les détails)
- `profile_too_large` : JSON importé > 1MB
- `ssrf_blocked` : redirection hors HuggingFace bloquée (protection SSRF)
- `hf_unavailable` : HuggingFace indisponible / réponse invalide
- `timeout` : délai dépassé (60s)
- `required_missing` : fichier requis manquant

## 7. Limitations (important)

- Les profils intégrés (`builtin`) ne peuvent pas être modifiés/supprimés. Utilisez `Dupliquer`.
- `id` est immuable. Pour renommer : `Dupliquer` → `Supprimer` l’ancien.
- Limite d’import : **1MB**.
- `Tester` n’autorise que les hôtes HuggingFace (allowlist SSRF) :
  - `huggingface.co`
  - `hf.co`
