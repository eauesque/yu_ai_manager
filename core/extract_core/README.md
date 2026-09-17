# core/extract_core

拡張パーサ向け抽出ヘルパ実装本体。

- `comfyui_extract_*.py`: ComfyUI JSON/CLIP/params 抽出
- `novelai_v4_extract_*.py`: NovelAI v4 解析/結果組み立て

依存方向: `extensions/*` -> `core/extract_core/*`
互換: 旧 `core/comfyui_extract*.py` と `core/novelai_v4_extract*.py` は再エクスポート
