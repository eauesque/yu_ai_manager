# core/tools/metadata

画像メタデータ抽出ロジックの実体。

- `extractor.py`: 入口 (`extract_metadata`) とCLI本体
- `formats.py`: 形式別抽出の集約
- `formats_novelai.py`: NovelAI系
- `formats_sd_comfy.py`: SD/A1111/ComfyUI系
- `formats_stealth.py`: stealth payload系
- `models.py`: model名/hash 抽出

依存方向: `metadata_extractor*.py` (compat) -> `core.tools.metadata.*`
