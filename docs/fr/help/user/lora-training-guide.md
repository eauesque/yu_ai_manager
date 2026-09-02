# Guide d'entraînement LoRA

Guide pratique complet pour créer des LoRA en langage naturel avec YU AI Manager + MCP + kohya_ss

---

## Introduction

Ce guide explique comment utiliser le serveur MCP de YU AI Manager avec kohya_ss pour créer des LoRA avec des instructions en langage naturel uniquement.

La majorité du travail dans la création traditionnelle de LoRA consistait en une **préparation manuelle du dataset**. Sélection des images, vérification et exclusion des tags, formatage des fichiers de caption, organisation de la structure des dossiers — tout cela était à la charge humaine.

Avec l'intégration MCP de YU AI Manager, ce flux de travail change. Une simple instruction comme « Créez un LoRA de ○○. Excluez les tags △△ » fait fonctionner l'ensemble du processus, de la collecte des matériaux au taggage, en passant par la génération du dataset et le lancement de kohya_ss.

---

## Flux global

Le processus de création de LoRA se compose de 5 étapes.

| Phase | Contenu | Responsable |
|---------|---------|------|
| 1. Préparation des matériaux | Collecte et placement des images d'entraînement | Humain / Agent IA |
| 2. Taggage | Taggage automatique par WD-Tagger | MCP (automatique) |
| 3. Génération du dataset | Création de projet, config des tags exclus, export | MCP (automatique) |
| 4. Exécution de l'entraînement | Lancement via appel kohya_ss | MCP (automatique) |
| 5. Vérification | Vérifier les résultats avec SD | Humain |

L'humain n'intervient que pour les décisions sur **quoi entraîner** et la vérification finale des résultats.

---

## Prérequis

### Logiciels requis

- YU AI Manager — inclut la fonctionnalité serveur MCP
- Claude Desktop ou Claude Code — client MCP
- kohya_ss — avec sd-scripts
- Stable Diffusion WebUI (A1111 / ComfyUI / Forge) — pour la vérification des résultats

### Exigences GPU

| VRAM GPU | Modèles compatibles | Paramètres requis |
|---------|----------|-----------|
| 8GB | SD 1.5 uniquement pratique | `--gradient_checkpointing` obligatoire |
| 12GB | SDXL fonctionne (avec limitations) | `--gradient_checkpointing` + `--cache_latents_to_disk` |
| 16GB | SDXL confortable | Fonctionne avec les paramètres par défaut |
| 24GB+ | SDXL et FLUX supportés | Pratiquement sans limitation |

### Structure des répertoires kohya_ss

```
O:\webui\kohya_ss\              ← Répertoire racine à configurer dans kohya_path
O:\webui\kohya_ss\venv\         ← Environnement virtuel Python (auto-détecté)
O:\webui\kohya_ss\sd-scripts\   ← Répertoire contenant les scripts d'entraînement
```

> **Attention** : YU AI Manager détecte automatiquement le sous-dossier `sd-scripts` et venv en spécifiant le répertoire racine dans `kohya_path`. Ne pas spécifier directement le chemin de sd-scripts.

---

## Configuration de YU AI Manager

### Paramètres de l'Extension

Saisir les informations suivantes dans l'onglet de paramètres du LoRA Dataset Manager.

| Paramètre | Description | Exemple |
|---------|------|---|
| `kohya_path` | Répertoire racine kohya_ss | `O:\webui\kohya_ss` |
| `output_base_dir` | Répertoire de base de sortie du dataset | `C:\lora_datasets` |
| `checkpoint_dir` | Répertoire des modèles de base | `O:\webui\models\Stable-diffusion` |
| `default_base_model` | Type de modèle par défaut | `sdxl` |

### Configuration WD-Tagger

Pour les datasets LoRA, la combinaison avec VLM (llava, etc.) n'est pas recommandée. VLM génère une grande quantité de tags en texte libre qui dégradent la qualité des captions.

```
engine_type: "onnx"  ← Utiliser ONNX seul
```

> **Attention** : Configurer `engine_type` sur `"both"` génère des tags composites VLM (`wooden_bear_and_fish_sculpture`, etc.). Ceux-ci ne fonctionnent pas comme captions kohya_ss et nuisent à l'entraînement.

---

## Procédure de création LoRA via MCP

### Étape 1 : Préparation des images sources

Placer les images d'entraînement dans la scan root de YU AI Manager et effectuer un scan.

- Ajouter le dossier d'entraînement dans les paramètres Scan Root de YU AI Manager
- Les images cibles sont enregistrées dans la DB après le scan
- Minimum 20~30 images, recommandé 50~200 images

### Étape 2 : Taggage avec WD-Tagger

Exécuter un taggage en masse depuis MCP.

```python
# Obtenir la liste des IDs de fichiers cibles et effectuer le taggage en masse
wd_tagger_batch(file_ids=[...], expected_count=N)
wait_for_batch(job_id="wd_tagger")
```

### Étape 3 : Création du projet

```python
create_lora_project(
    name="carved_bear",
    concept="carved_bear",   # Utilisé pour le nom de dossier kohya_ss
    base_model="sdxl",
    repeat=20
)
```

### Étape 4 : Configuration des fichiers et tags

Définir les IDs de fichiers dans le projet et vérifier les statistiques des tags.

```python
update_lora_project(project_id=N, file_ids=[...])
get_lora_project_tags(project_id=N)
```

#### Philosophie de conception des tags exclus

C'est ici que se trouve l'essence de « quoi enseigner à la LoRA ».

**Tags à conserver** : Caractéristiques uniques du concept à apprendre (forme, style, éléments propres)

**Tags à exclure** : Tags génériques connus du modèle (`no_humans`, `realistic`, `animal`, fond, etc.)

Exemple pour une LoRA d'ours sculpté en bois :

- Conserver : `bear`, `fish`, `statue`, `sculpture`, `standing`, `full_body`, `open_mouth`
- Exclure : `no_humans`, `animal_focus`, `animal`, `realistic`, `simple_background`, `solo`, `indoors`, `shadow`...

### Étape 5 : Vérification de la prévisualisation de caption

```python
preview_lora_caption(project_id=N, file_id=un_id_fichier)
```

Exemple de sortie :

```
"fish, full_body, open_mouth, standing"
```

Vérifier l'absence de bruit VLM et l'obtention d'une liste de tags simple.

### Model Scope

Each project has a `model_scope` setting that controls which WD-Tagger model is used for captions, preview, and export.

- `active` (default for new projects): Use tags from the active WD model only. If no active model is set, it falls back to all models.
- `all` (default for existing projects): Mix tags from all models.
- `<model_id>` (for example, `wd-eva02-large-tagger-v3`): Use tags from the explicitly selected model only.

For files tagged by multiple models, `active` is usually sufficient. When you need an explicit model for comparison or validation, use the same model_id shown in the WD-Tagger profile dropdown on the Tools page.

### Étape 6 : Export du Dataset

```python
export_lora_dataset(project_id=N)
```

Structure du dossier de sortie :

```
{output_base_dir}/{project_name}/{repeat}_{concept}/
    image001.jpeg
    image001.txt   ← caption
    image002.jpeg
    image002.txt
```

### Étape 7 : Exécution de l'entraînement

D'abord vérifier la commande avec dry_run.

```python
preview_lora_train_command(
    project_id=N,
    checkpoint="chemin_complet\checkpoint.safetensors"
)
```

Lancer l'entraînement si pas de problème.

```python
start_lora_training(
    project_id=N,
    checkpoint="chemin_complet\checkpoint.safetensors",
    extra_args=["--gradient_checkpointing", "--xformers", "--cache_latents_to_disk"]
)
```

Vérification de la progression :

```python
get_lora_train_status(project_id=N, tail=20)
```

---

## Paramètres d'entraînement par défaut

| Paramètre | Valeur par défaut | Description |
|-----------|------------|------|
| `network_dim` | 32 | Rang de la LoRA. Plus élevé = plus d'expressivité mais fichier plus grand |
| `network_alpha` | 16 | Généralement défini à la moitié de dim |
| `learning_rate` | 1e-4 | Taux d'apprentissage |
| `max_train_epochs` | 10 | Nombre d'époques |
| `save_every_n_epochs` | 2 | Intervalle de sauvegarde intermédiaire |
| `mixed_precision` | fp16 | Précision. bf16 peut économiser de la VRAM |
| `resolution` | 1024,1024 (SDXL) | Résolution d'entraînement. SD1.5 : 512,512 |

---

## Paramètres recommandés par GPU

| VRAM GPU | extra_args recommandés |
|---------|---------------|
| 8GB | `--gradient_checkpointing --xformers --cache_latents_to_disk --optimizer_type=AdamW8bit` |
| 12GB | `--gradient_checkpointing --xformers --cache_latents_to_disk` |
| 16GB | (fonctionne avec les valeurs par défaut) |
| 24GB+ | (fonctionne avec les valeurs par défaut, batch_size peut être augmenté) |

---

## Dépannage

### `ModuleNotFoundError: No module named 'torch'`

**Cause** : Tentative d'exécution des scripts kohya_ss dans le venv de YU AI Manager.

**Solution** : Définir `kohya_path` sur le répertoire racine (parent de sd-scripts). YU AI Manager détecte automatiquement `kohya_path/venv/Scripts/python.exe`.

---

### `torch.OutOfMemoryError: CUDA out of memory`

**Solution** : Ajouter les éléments suivants dans `extra_args` :

```python
extra_args=["--gradient_checkpointing", "--xformers", "--cache_latents_to_disk"]
```

---

### Contamination par des tags de bruit VLM

**Cause** : `engine_type` est sur `"both"`, VLM (llava, etc.) génère des tags en texte libre.

**Solution** : Changer `engine_type` sur `"onnx"` dans les paramètres WD-Tagger, supprimer tous les tags et re-tagger.

```python
wd_tagger_save_config({"engine_type": "onnx"})
wd_tagger_delete_tags_batch(file_ids=[...], expected_count=N)
wd_tagger_batch(file_ids=[...], expected_count=N)
```

---

## Prompt de génération

### Composition de base du prompt

```
{concept_token}, {tags_caractéristiques}, <lora:{lora_name}:{strength}>
```

Exemple pour une LoRA d'ours sculpté en bois :

```
carved_bear, wooden sculpture, bear statue, wood texture, brown,
full_body, standing, open_mouth, fish, simple_background,
<lora:carved_bear:0.7>
```

### Ajustement de la force de la LoRA

| Force | Caractéristiques |
|-----|------|
| 0.5~0.6 | Forte influence du modèle de base. Couleur et style proches du modèle de base |
| 0.7~0.8 | Plage recommandée. Bon équilibre entre caractéristiques LoRA et modèle de base |
| 0.9~1.0 | Forte influence de la LoRA. La forme ressort mais les couleurs tendent vers le blanc/crème |
