# LoRA Training Guide

Complete guide to natural-language LoRA training with YU AI Manager + MCP + kohya_ss

---

## Introduction

This guide explains the workflow for creating LoRAs using YU AI Manager's MCP server integration with kohya_ss, driven entirely by natural-language instructions.

The bulk of traditional LoRA creation time was spent on manual dataset preparation: selecting images, reviewing and filtering tags, formatting caption files, organizing folder structure — all done by hand.

YU AI Manager's MCP integration changes this. A single instruction like "Create a LoRA for X, excluding tags Y and Z" drives the entire pipeline: from image tagging and dataset generation through launching kohya_ss training.

---

## Overall Workflow

LoRA creation consists of five stages:

| Phase | Task | Responsibility |
|-------|------|---------------|
| 1. Source Preparation | Collect and place training images | Human / AI agent |
| 2. Tagging | Automatic tagging via WD-Tagger | MCP (automatic) |
| 3. Dataset Generation | Create project, set excluded tags, export | MCP (automatic) |
| 4. Training | Call kohya_ss and run training | MCP (automatic) |
| 5. Verification | Test LoRA in SD and check results | Human |

Human involvement is limited to deciding what to train and verifying the final result.

---

## Prerequisites

### Required Software

- YU AI Manager — includes MCP server functionality
- Claude Desktop or Claude Code — MCP client
- kohya_ss — must include sd-scripts
- Stable Diffusion WebUI (A1111 / ComfyUI / Forge) — for result verification

### GPU Requirements

| GPU VRAM | Supported Models | Required Settings |
|---------|-----------------|-------------------|
| 8GB | SD 1.5 only (practical) | `--gradient_checkpointing` required |
| 12GB | SDXL works (with limits) | `--gradient_checkpointing` + `--cache_latents_to_disk` |
| 16GB | SDXL comfortable | Works with default settings |
| 24GB+ | SDXL and FLUX both supported | Almost no restrictions |

> **Note**: SDXL LoRA training on an RTX 3060 12GB is possible, but gradient_checkpointing is required, so 24,000 steps takes approximately 10 hours. An RTX 5060 Ti 16GB is estimated to reduce this to 3–5 hours.

### kohya_ss Directory Structure

kohya_ss often separates the top-level directory from the actual script directory:

```
O:\webui\kohya_ss\              ← Top directory to set as kohya_path
O:\webui\kohya_ss\venv\         ← Python virtual environment (auto-detected)
O:\webui\kohya_ss\sd-scripts\   ← Directory containing training scripts
```

> ⚠️ **Note**: Specify the top-level directory as `kohya_path` — YU AI Manager auto-detects the `sd-scripts` subfolder and venv. Do not point directly to sd-scripts.

---

## YU AI Manager Settings

### Extension Configuration

Enter the following in the LoRA Dataset Manager settings tab:

| Setting | Description | Example |
|---------|-------------|---------|
| `kohya_path` | kohya_ss top directory | `O:\webui\kohya_ss` |
| `output_base_dir` | Base directory for dataset output | `C:\lora_datasets` |
| `checkpoint_dir` | Directory containing base model checkpoints | `O:\webui\models\Stable-diffusion` |
| `default_base_model` | Default model type | `sdxl` |

### WD-Tagger Settings

Using VLMs (llava, etc.) alongside WD-Tagger is not recommended for LoRA datasets. VLMs generate large numbers of free-form tags that degrade caption quality.

```
engine_type: "onnx"  ← Use ONNX only
```

> ⚠️ **Note**: Setting `engine_type` to `"both"` causes VLM-derived compound tags (e.g., `wooden_bear_and_fish_sculpture`) to be generated. These do not function as kohya_ss captions and will impede training.

---

## LoRA Creation Steps via MCP

### Step 1: Prepare Source Images

Place training images in YU AI Manager's scan root and scan them.

- Add the training folder in YU AI Manager's Scan Root settings
- After scanning completes, target images are registered in the DB
- Minimum 20–30 images; recommended 50–200 images

> **Note**: Image quality is the single biggest determinant of training outcome. Choose images with resolution of 512px or higher where the subject is clearly visible.

### Step 2: Tag with WD-Tagger

Run batch tagging from MCP:

```python
# Get list of target file IDs and batch tag them
wd_tagger_batch(file_ids=[...], expected_count=N)
wait_for_batch(job_id="wd_tagger")
```

If existing tags are present, delete them first:

```python
wd_tagger_delete_tags_batch(file_ids=[...], expected_count=N)
```

### Step 3: Create Project

```python
create_lora_project(
    name="carved_bear",
    concept="carved_bear",   # Used as kohya_ss folder name
    base_model="sdxl",
    repeat=20
)
```

### Step 4: Configure Files and Tags

Set file IDs on the project and review the tag summary:

```python
update_lora_project(project_id=N, file_ids=[...])
get_lora_project_tags(project_id=N)
```

Review the tag summary to decide which tags to exclude.

#### Tag Exclusion Strategy

This is the core of deciding what the LoRA will learn.

**Tags to keep**: Features unique to the concept you want to train (form, style, characteristic elements)

**Tags to exclude**: Generic tags the base model already knows (`no_humans`, `realistic`, `animal`, `solo`, background-related tags, etc.)

Example — carved wooden bear LoRA:

- Keep: `bear`, `fish`, `statue`, `sculpture`, `standing`, `full_body`, `open_mouth`
- Exclude: `no_humans`, `animal_focus`, `animal`, `realistic`, `simple_background`, `solo`, `indoors`, `shadow`...

> ⚠️ **Note**: Failing to isolate the concept causes training to scatter. If you want to retain `bear` or `wood`, be aware that WD-Tagger ONNX may not reliably assign these. Verify actual output via caption preview.

```python
update_lora_project(
    project_id=N,
    tag_exclude=["no_humans", "animal_focus", "animal", "realistic", ...]
)
```

### Step 5: Preview Captions

```python
preview_lora_caption(project_id=N, file_id=<any_file_id>)
```

Example output:

```
"fish, full_body, open_mouth, standing"
```

Confirm that the output is a clean, simple tag list with no VLM noise. If many captions are empty, revisit the excluded tags.

### Model Scope

Each project has a `model_scope` setting that controls which WD-Tagger model is used for captions, preview, and export.

- `active` (default for new projects): Use tags from the active WD model only. If no active model is set, it falls back to all models.
- `all` (default for existing projects): Mix tags from all models.
- `<model_id>` (for example, `wd-eva02-large-tagger-v3`): Use tags from the explicitly selected model only.

For files tagged by multiple models, `active` is usually sufficient. When you need an explicit model for comparison or validation, use the same model_id shown in the WD-Tagger profile dropdown on the Tools page.

### Step 6: Export Dataset

```python
export_lora_dataset(project_id=N)
```

Output folder structure:

```
{output_base_dir}/{project_name}/{repeat}_{concept}/
    image001.jpeg
    image001.txt   ← caption
    image002.jpeg
    image002.txt
```

### Step 7: Run Training

First, preview the command with a dry run:

```python
preview_lora_train_command(
    project_id=N,
    checkpoint="full\path\to\checkpoint.safetensors"
)
```

If everything looks correct, start training:

```python
start_lora_training(
    project_id=N,
    checkpoint="full\path\to\checkpoint.safetensors",
    extra_args=["--gradient_checkpointing", "--xformers", "--cache_latents_to_disk"]
)
```

Check progress:

```python
get_lora_train_status(project_id=N, tail=20)
```

---

## Default Training Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `network_dim` | 32 | LoRA rank. Higher = more expressive but larger file size |
| `network_alpha` | 16 | Typically set to half of dim |
| `learning_rate` | 1e-4 | Learning rate |
| `max_train_epochs` | 10 | Number of epochs |
| `save_every_n_epochs` | 2 | Interval for intermediate saves |
| `mixed_precision` | fp16 | Precision. bf16 can save more VRAM in some cases |
| `resolution` | 1024,1024 (SDXL) | Training resolution. SD1.5 uses 512,512 |

> **Note**: These can be changed in the Settings tab or via `set_extension_config`. Additional arguments can be passed via `extra_args` in `start_lora_training`.

---

## Recommended Settings by GPU

| GPU VRAM | Recommended extra_args |
|---------|----------------------|
| 8GB | `--gradient_checkpointing --xformers --cache_latents_to_disk --optimizer_type=AdamW8bit` |
| 12GB | `--gradient_checkpointing --xformers --cache_latents_to_disk` |
| 16GB | (works with defaults) |
| 24GB+ | (works with defaults; batch_size can be increased) |

> ⚠️ **Note**: Using gradient_checkpointing on a 12GB GPU means ~10–12 hours for 24,000 SDXL steps. 16GB+ removes this constraint and significantly speeds up training.

---

## Repeat Count and Epoch Guidelines

**Total training steps = image count × repeat × epoch count**

| Concept Complexity | Recommended Steps | Example (50 images) |
|-------------------|------------------|---------------------|
| Simple object or style | 1,000–3,000 | repeat=10, epoch=5 |
| Character or sculptural object | 3,000–8,000 | repeat=20, epoch=5 |
| Complex style or person | 5,000–15,000 | repeat=20, epoch=10 |

> **Note**: Training with 120 images × 20 repeat × 10 epochs = 24,000 steps produces good quality results. However, 5–6 epochs may yield equivalent results, so trying fewer epochs first is recommended.

---

## Troubleshooting

### ModuleNotFoundError: No module named 'torch'

**Cause**: YU AI Manager is trying to run kohya_ss scripts from within its own venv.

**Fix**: Set `kohya_path` to the top-level directory (parent of sd-scripts). YU AI Manager auto-detects `kohya_path/venv/Scripts/python.exe`.

---

### AssertionError: resolution is required

**Cause**: `--resolution` was not specified.

**Fix**: The latest version of YU AI Manager adds this automatically (SDXL: 1024,1024; SD1.5: 512,512).

---

### AssertionError: network for Text Encoder cannot be trained with caching

**Cause**: `--cache_text_encoder_outputs` and `--network_train_unet_only` are not paired.

**Fix**: The latest version of YU AI Manager automatically adds `--network_train_unet_only` for SDXL.

---

### torch.OutOfMemoryError: CUDA out of memory

**Cause**: Insufficient VRAM.

**Fix**: Add the following to `extra_args`:

```python
extra_args=["--gradient_checkpointing", "--xformers", "--cache_latents_to_disk"]
```

---

### VLM Noise Tags in Captions

**Cause**: `engine_type` is set to `"both"`, causing a VLM (llava, etc.) to generate free-form tags.

**Fix**: Change to `engine_type="onnx"` in WD-Tagger settings, delete all tags, and re-tag.

```python
wd_tagger_save_config({"engine_type": "onnx"})
wd_tagger_delete_tags_batch(file_ids=[...], expected_count=N)
wd_tagger_batch(file_ids=[...], expected_count=N)
```

---

### checkpoint must be inside checkpoint_dir (403 error)

**Cause**: The checkpoint path points outside of `checkpoint_dir`.

**Fix**: Verify that `checkpoint_dir` in Extension settings points to the correct directory.

---

### output_base_dir not configured (400 error)

**Cause**: `output_base_dir` in Extension settings is not set or not saved.

**Fix**: Re-save in the UI settings tab, or set via `set_extension_config` from MCP.

---

## Generation Prompts

### Basic Prompt Structure

```
{concept_token}, {feature_tags}, <lora:{lora_name}:{strength}>
```

Example for a carved wooden bear LoRA:

```
carved_bear, wooden sculpture, bear statue, wood texture, brown,
full_body, standing, open_mouth, fish, simple_background,
<lora:carved_bear:0.7>
```

Negative prompt:

```
blurry, lowres, bad anatomy, worst quality, flat color, monochrome
```

### Adjusting LoRA Strength

| Strength | Characteristics |
|----------|----------------|
| 0.5–0.6 | Base model has stronger influence; color and style lean toward base model |
| 0.7–0.8 | Recommended range; good balance between LoRA features and base model |
| 0.9–1.0 | LoRA has strong influence; form comes through but colors tend toward white/cream |

> **Note**: If colors are washing out to white, lower the strength or add `brown wood, warm tone` to the prompt to guide the color.

---

## Future Extensions

### Automating Source Collection

Currently, source images must be prepared manually. Using a browser agent like Claude in Chrome, you can automate this with instructions like "collect images of X from the web and put them in a folder."

Using YU AI Manager's own generated images as training source is also effective — images generated by SD/ComfyUI/NAI can be recycled directly as LoRA training material.

### Mass LoRA Production Flow

With MCP + Claude Desktop, full automation is achievable:

1. Collect source images from the web (Claude in Chrome)
2. Scan and tag in YU AI Manager (MCP)
3. Create project, configure excluded tags, export (MCP)
4. Launch kohya_ss training (MCP)
5. Give instructions before bed → LoRA complete by morning

### Choosing a Base Model

Illustrious-based models like waiSHUFFLENOOB are optimized for anime-style generation. Training on photographic subjects (e.g., carved wooden bears) tends to produce white/cream color casts.

For photorealistic quality, use a realisticPhoto-type base model. The LoRA must be used with the same model it was trained on.

---

## Summary

The YU AI Manager + MCP + kohya_ss workflow significantly reduces the time and effort required to create LoRAs.

- Full epoch training from source images runs to completion from MCP instructions alone
- The entire workflow operates from natural-language instructions
- Generated images clearly express the learned subject's form

The only remaining manual step is source image collection, which can be automated by combining with browser agents, making full end-to-end automation achievable.
