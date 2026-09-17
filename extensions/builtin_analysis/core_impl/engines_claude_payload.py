import base64
import io
from pathlib import Path

# Format accepted by both OpenAI / Claude Vision API
_NATIVE_FORMATS = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def encode_image(image_path: Path) -> tuple[str, str]:
    """Encode image as base64 for OpenAI / Claude Vision API.

    Natively supported formats (PNG, JPEG, WebP, GIF) are sent as-is.
    Other formats (AVIF, BMP, TIFF, HEIF, JXL, etc.) are converted to
    PNG via Pillow before encoding, matching the Ollama engine behaviour.
    """
    ext = image_path.suffix.lower()
    media_type = _NATIVE_FORMATS.get(ext)
    if media_type:
        with open(image_path, "rb") as f:
            data = base64.standard_b64encode(f.read()).decode("utf-8")
        return media_type, data

    # Unsupported format -- convert to PNG
    from PIL import Image

    with Image.open(image_path) as img:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
    data = base64.standard_b64encode(buf.getvalue()).decode("utf-8")
    return "image/png", data


_PROMPT_LANG = {
    "ja": {
        "instruction": "この画像を分析してください。以下のJSON形式で回答してください。他のテキストは不要です。",
        "existing_tags": "既存タグ",
        "gen_prompt": "生成プロンプト",
        "desc_hint": "画像の内容説明（日本語、何が描かれているか、シーンの状況を2-3文で）",
        "tags_hint": "検出されたタグ（英語、Danbooru形式、最大20個）",
        "quality_hint": "0-10の品質スコア（構図、色彩、描画品質を総合評価）",
        "quality_notes_hint": "品質についての短いコメント（日本語）",
        "palette_hint": "主要な3-5色（英語）",
        "suggestion_hint": "プロンプト改善の提案（日本語、50文字以内）",
    },
    "en": {
        "instruction": "Analyze this image. Respond ONLY with JSON in the format below, no other text.",
        "existing_tags": "Existing tags",
        "gen_prompt": "Generation prompt",
        "desc_hint": "Image description (English, what is depicted, scene context in 2-3 sentences)",
        "tags_hint": "Detected tags (English, Danbooru-style, max 20)",
        "quality_hint": "0-10 quality score (composition, color, drawing quality)",
        "quality_notes_hint": "Short quality comment (English)",
        "palette_hint": "3-5 dominant colors (English)",
        "suggestion_hint": "Prompt improvement suggestion (English, max 50 chars)",
    },
    "zh": {
        "instruction": "请分析这张图片。仅以下方的JSON格式回答，不要其他文字。",
        "existing_tags": "现有标签",
        "gen_prompt": "生成提示词",
        "desc_hint": "图片内容描述（中文，描绘了什么，场景情况，2-3句话）",
        "tags_hint": "检测到的标签（英语，Danbooru格式，最多20个）",
        "quality_hint": "0-10品质评分（构图、色彩、绘画品质综合评估）",
        "quality_notes_hint": "品质简评（中文）",
        "palette_hint": "3-5种主要颜色（英语）",
        "suggestion_hint": "提示词改进建议（中文，50字以内）",
    },
    "ko": {
        "instruction": "이 이미지를 분석해 주세요. 아래 JSON 형식으로만 응답하고 다른 텍스트는 포함하지 마세요.",
        "existing_tags": "기존 태그",
        "gen_prompt": "생성 프롬프트",
        "desc_hint": "이미지 내용 설명 (한국어, 무엇이 묘사되었는지, 장면 상황을 2-3문장으로)",
        "tags_hint": "감지된 태그 (영어, Danbooru 형식, 최대 20개)",
        "quality_hint": "0-10 품질 점수 (구도, 색채, 그림 품질 종합 평가)",
        "quality_notes_hint": "품질에 대한 짧은 코멘트 (한국어)",
        "palette_hint": "주요 3-5색 (영어)",
        "suggestion_hint": "프롬프트 개선 제안 (한국어, 50자 이내)",
    },
}

_TRENDS_LANG = {
    "ja": {
        "instruction": "以下はAI画像生成のプロンプト{count}件です。傾向を分析して以下のJSON形式で回答してください。",
        "prompts_label": "プロンプト",
        "freq_tags": "よく使われるタグTOP10",
        "style_tendency": "全体的なスタイルの傾向（日本語）",
        "strengths": "プロンプトの強み（日本語）",
        "weaknesses": "改善可能な点（日本語）",
        "recommendations": "具体的な改善提案3-5個（日本語）",
        "unexplored": "試していなさそうなテーマや手法3-5個",
    },
    "en": {
        "instruction": "Below are {count} AI image generation prompts. Analyze the trends and respond in the JSON format below.",
        "prompts_label": "Prompts",
        "freq_tags": "Top 10 frequently used tags",
        "style_tendency": "Overall style tendency (English)",
        "strengths": "Prompt strengths (English)",
        "weaknesses": "Areas for improvement (English)",
        "recommendations": "3-5 specific improvement suggestions (English)",
        "unexplored": "3-5 unexplored themes or techniques",
    },
    "zh": {
        "instruction": "以下是{count}条AI图像生成提示词。请分析趋势并以下方JSON格式回答。",
        "prompts_label": "提示词",
        "freq_tags": "最常用标签TOP10",
        "style_tendency": "整体风格倾向（中文）",
        "strengths": "提示词的优点（中文）",
        "weaknesses": "可改进之处（中文）",
        "recommendations": "3-5个具体改进建议（中文）",
        "unexplored": "尚未尝试的主题或手法3-5个",
    },
    "ko": {
        "instruction": "아래는 AI 이미지 생성 프롬프트 {count}건입니다. 트렌드를 분석하고 아래 JSON 형식으로 응답해 주세요.",
        "prompts_label": "프롬프트",
        "freq_tags": "자주 사용되는 태그 TOP10",
        "style_tendency": "전체적인 스타일 경향 (한국어)",
        "strengths": "프롬프트의 장점 (한국어)",
        "weaknesses": "개선 가능한 점 (한국어)",
        "recommendations": "구체적인 개선 제안 3-5개 (한국어)",
        "unexplored": "시도하지 않은 테마나 기법 3-5개",
    },
}


_SYSTEM_LANG = {
    "ja": (
        "あなたは画像分析の専門家です。"
        "回答は必ずJSON形式で、description, quality_notes, prompt_suggestion の値は必ず日本語で記述してください。"
        "英語で回答してはいけません。タグと色名のみ英語です。"
    ),
    "en": (
        "You are an image analysis expert. "
        "Respond ONLY in JSON. All text values (description, quality_notes, prompt_suggestion) MUST be in English."
    ),
    "zh": (
        "你是图像分析专家。"
        "回答必须为JSON格式，description、quality_notes、prompt_suggestion 的值必须用中文。"
        "不要用英文回答。只有标签和颜色名使用英文。"
    ),
    "ko": (
        "당신은 이미지 분석 전문가입니다. "
        "반드시 JSON 형식으로 응답하고, description, quality_notes, prompt_suggestion 값은 반드시 한국어로 작성하세요. "
        "영어로 응답하지 마세요. 태그와 색상명만 영어입니다."
    ),
}


def get_system_prompt(language: str = "ja") -> str:
    """Return the system prompt for the specified language."""
    return _SYSTEM_LANG.get(language, _SYSTEM_LANG["en"])


_SIMPLE_PROMPT_LANG = {
    "ja": {
        "instruction": "この画像の色彩と構図だけを分析してください。以下のJSON形式で回答してください。他のテキストは不要です。",
        "palette_hint": "主要な3-5色（英語）",
        "comp_hint": "構図の詳細な説明（日本語、ライティング・配置・視線誘導を含む、2-3文）",
        "mood_hint": "画像全体の雰囲気（日本語、1文）",
    },
    "en": {
        "instruction": "Analyze ONLY the color palette and composition of this image. Respond with JSON below, no other text.",
        "palette_hint": "3-5 dominant colors (English)",
        "comp_hint": "Detailed composition description (English, lighting, placement, visual flow, 2-3 sentences)",
        "mood_hint": "Overall mood of the image (English, 1 sentence)",
    },
    "zh": {
        "instruction": "仅分析这张图片的色彩和构图。以下方的JSON格式回答，不要其他文字。",
        "palette_hint": "3-5种主要颜色（英语）",
        "comp_hint": "构图详细描述（中文，光线、布局、视觉引导，2-3句话）",
        "mood_hint": "图片整体氛围（中文，1句话）",
    },
    "ko": {
        "instruction": "이 이미지의 색채와 구도만 분석해 주세요. 아래 JSON 형식으로만 응답하세요.",
        "palette_hint": "주요 3-5색 (영어)",
        "comp_hint": "구도 상세 설명 (한국어, 조명, 배치, 시선 유도, 2-3문장)",
        "mood_hint": "이미지 전체 분위기 (한국어, 1문장)",
    },
}


def build_image_prompt(existing_tags: list[str] | None = None, existing_prompt: str | None = None,
                       language: str = "ja", mode: str = "full") -> str:
    if mode == "simple":
        return _build_simple_prompt(language)

    # OCR mode: use existing_prompt directly as VLM prompt
    if mode == "ocr" and existing_prompt:
        return existing_prompt

    lang = _PROMPT_LANG.get(language, _PROMPT_LANG["en"])
    context = ""
    if existing_tags:
        context += f"\n{lang['existing_tags']}: {', '.join(existing_tags[:30])}"
    if existing_prompt:
        context += f"\n{lang['gen_prompt']}: {existing_prompt[:500]}"

    lang_reminder = ""
    if language == "ja":
        lang_reminder = "\n\n重要: description, quality_notes, prompt_suggestion は必ず日本語で書いてください。"
    elif language == "zh":
        lang_reminder = "\n\n重要: description, quality_notes, prompt_suggestion 必须用中文。"
    elif language == "ko":
        lang_reminder = "\n\n중요: description, quality_notes, prompt_suggestion은 반드시 한국어로 작성하세요."

    return f"""{lang['instruction']}
{context}{lang_reminder}

{{
  "description": "{lang['desc_hint']}",
  "tags": ["{lang['tags_hint']}"],
  "quality_score": {lang['quality_hint']},
  "quality_notes": "{lang['quality_notes_hint']}",
  "style": "anime/realistic/sketch/watercolor/pixel_art/3d_render",
  "composition": "portrait/full_body/close_up/landscape/group/action_pose",
  "mood": "cheerful/dark/serene/dynamic/romantic/mysterious",
  "color_palette": ["{lang['palette_hint']}"],
  "prompt_suggestion": "{lang['suggestion_hint']}"
}}"""


def _build_simple_prompt(language: str = "ja") -> str:
    lang = _SIMPLE_PROMPT_LANG.get(language, _SIMPLE_PROMPT_LANG["en"])
    return f"""{lang['instruction']}

{{
  "color_palette": ["{lang['palette_hint']}"],
  "composition": "{lang['comp_hint']}",
  "mood": "{lang['mood_hint']}"
}}"""


def build_image_messages(media_type: str, image_data: str, prompt: str) -> list[dict]:
    return [
        {
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_data}},
                {"type": "text", "text": prompt},
            ],
        }
    ]


def build_trends_prompt(prompt_texts: list[str], language: str = "ja") -> str:
    lang = _TRENDS_LANG.get(language, _TRENDS_LANG["en"])
    return f"""{lang['instruction'].format(count=len(prompt_texts))}

{lang['prompts_label']}:
{chr(10).join(f'- {t}' for t in prompt_texts[:30])}

{{
  "frequent_tags": ["{lang['freq_tags']}"],
  "style_tendency": "{lang['style_tendency']}",
  "strengths": "{lang['strengths']}",
  "weaknesses": "{lang['weaknesses']}",
  "recommendations": ["{lang['recommendations']}"],
  "unexplored": ["{lang['unexplored']}"]
}}"""
