# WD-Tagger Profile UI Guide

This document explains how to use the WD-Tagger **Profile Manager UI** (added in v4.197.0+).

## 1. Overview

- A **profile** bundles WD-Tagger settings such as model files, tag definitions, thresholds, and preprocessing.
- Open it from the Tools page → **WD-Tagger** section → click `Manage profiles...`.
- Inside the modal, you switch between the **List** view and the **Form** view.

## 2. List View

### 2.1 Badges (Builtin / User)

- `builtin` badge: built-in profiles (read-only)
- `user` badge: user profiles (you can create/edit/delete)
- `↻` marker: this profile **overrides a built-in** profile with the same `id`

### 2.2 Filter (All / User / Builtin)

Use the filter buttons at the top:

- `All`
- `User`
- `Builtin`

### 2.3 Buttons (Actions)

Row actions:

- `Duplicate`: copy a profile and open it in the form (use this to customize a built-in profile)
- `Edit`: edit a user profile (built-in profiles cannot be edited)
- `Delete`: delete a user profile (built-in profiles cannot be deleted)
- `Export`: download the profile as a `.json`
- `Test`: **dry-run download** to verify required files can be fetched from HuggingFace

Top-right actions:

- `+ New`: create an empty new profile
- `Import`: create a profile from existing JSON (Upload / Paste)

## 3. Form View

The form is organized into 5 accordion sections.

### 3.1 Metadata

- `id`: profile identifier (cannot be changed later)
- `Display name`: name shown in the list
- `profile_version`: profile schema version (usually leave as-is)

### 3.2 Model & Files

- `model_id`: HuggingFace model id (example: `SmilingWolf/wd-swinv2-tagger-v3`)
- `adapter_family`: adapter family (only if needed)
- `backend`: backend selection (only if needed)
- `hf_subdir`: subdirectory inside the HuggingFace repo (only if needed)
- `Files`:
  - `name`: file name to download (example: `model.onnx`)
  - `Required`: if checked, `Test` treats the file as mandatory
  - `size_hint_mb`: optional size hint
  - `+ Add file` / `Remove`: add/remove rows

### 3.3 Tag source

Choose where tag definitions are loaded from.

- `csv`:
  - `File (file)`: pick a file from `files`
  - `Delimiter (delimiter)`: e.g. `,`
  - `Name column (name_col)`: column name for tag names
  - `Category column (category_col)`: optional category column
  - `Category map (category_map)`: optional normalization mapping
- `json_list`:
  - `File (file)`
  - `Schema (schema)`: only if needed
- `json_dict`:
  - `File (file)`
  - `Mapping (mapping)`: only if needed
- `composite`:
  - `Sources (sources)`: how to combine multiple sources

### 3.4 Threshold source

Choose where thresholds are loaded from.

- `global_per_category`: set per-category thresholds directly in the UI (`General` / `Character` / `Copyright` / `Artist` / `Meta`)
- `per_tag`: reference a file and define fallback behavior
  - `File (file)`: per-tag threshold file
  - `Fallback mode (fallback.mode)`: `global` / `category_default`
  - `Fallback value (fallback.value)`: default value when unavailable

### 3.5 Preprocess & Categories

Preprocess parameters and category settings.

- Preprocess (`preprocess_spec`):
  - `input_size`, `dtype`, `layout`, `channel_order`, `resize_strategy` (`letterbox` / `longest_side_pad` / `stretch`), `scale`
  - `mean` / `std`: 3-element normalization vectors
- Categories:
  - `Supported categories`: which categories are enabled
  - `categories_mode`: `from_tag_source` / `all_general`

## 4. Import / Export

### 4.1 Import

Click `Import` to open a modal with two tabs:

- `Upload JSON`: upload a `.json` file
- `Paste JSON`: paste JSON into the text area

After import, the form opens. Review/adjust the content and then click `Save`.

### 4.2 Export

Use `Export` in the list to download the selected profile as JSON.

## 5. Test (dry-run download)

- `Test` verifies that the files listed in `files` can be fetched from **HuggingFace**, without doing a real model download.
- On success, you may see a banner like `Downloaded OK: {n} files ({total} MB)`.
- On failure, a banner explains the reason (see the next section).

## 6. Common Errors (Short Explanations)

- `id_conflict`: a user profile with the same `id` already exists
- `id_immutable`: `id` cannot be changed (rename via Duplicate → Delete)
- `in_use`: cannot delete because the profile is currently active
- `validation_failed`: JSON / form values failed schema validation (`{detail}` contains details)
- `profile_too_large`: imported JSON exceeds the 1MB cap
- `ssrf_blocked`: redirect outside HuggingFace was blocked (SSRF protection)
- `hf_unavailable`: HuggingFace is unavailable or returned an invalid response
- `timeout`: download check timed out (60s)
- `required_missing`: a required file is missing (a file marked `Required`)

## 7. Limitations (Important)

- Built-in (`builtin`) profiles cannot be edited/deleted. Use `Duplicate` to create a user copy.
- `id` is immutable. To rename: `Duplicate` → `Delete` the old one.
- Imported profile JSON is limited to **1MB**.
- `Test` only allows HuggingFace hosts (SSRF allowlist):
  - `huggingface.co`
  - `hf.co`
