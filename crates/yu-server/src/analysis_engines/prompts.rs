use super::AnalyzeMode;

struct PromptLang {
    instruction: &'static str,
    existing_tags: &'static str,
    gen_prompt: &'static str,
    desc_hint: &'static str,
    tags_hint: &'static str,
    quality_hint: &'static str,
    quality_notes_hint: &'static str,
    palette_hint: &'static str,
    suggestion_hint: &'static str,
}

struct SimplePromptLang {
    instruction: &'static str,
    palette_hint: &'static str,
    comp_hint: &'static str,
    mood_hint: &'static str,
}

struct TrendsLang {
    instruction: &'static str,
    prompts_label: &'static str,
    freq_tags: &'static str,
    style_tendency: &'static str,
    strengths: &'static str,
    weaknesses: &'static str,
    recommendations: &'static str,
    unexplored: &'static str,
}

const PROMPT_JA: PromptLang = PromptLang {
    instruction:
        "この画像を分析してください。以下のJSON形式で回答してください。他のテキストは不要です。",
    existing_tags: "既存タグ",
    gen_prompt: "生成プロンプト",
    desc_hint: "画像の内容説明（日本語、何が描かれているか、シーンの状況を2-3文で）",
    tags_hint: "検出されたタグ（英語、Danbooru形式、最大20個）",
    quality_hint: "0-10の品質スコア（構図、色彩、描画品質を総合評価）",
    quality_notes_hint: "品質についての短いコメント（日本語）",
    palette_hint: "主要な3-5色（英語）",
    suggestion_hint: "プロンプト改善の提案（日本語、50文字以内）",
};
const PROMPT_EN: PromptLang = PromptLang {
    instruction: "Analyze this image. Respond ONLY with JSON in the format below, no other text.",
    existing_tags: "Existing tags",
    gen_prompt: "Generation prompt",
    desc_hint: "Image description (English, what is depicted, scene context in 2-3 sentences)",
    tags_hint: "Detected tags (English, Danbooru-style, max 20)",
    quality_hint: "0-10 quality score (composition, color, drawing quality)",
    quality_notes_hint: "Short quality comment (English)",
    palette_hint: "3-5 dominant colors (English)",
    suggestion_hint: "Prompt improvement suggestion (English, max 50 chars)",
};
const PROMPT_ZH: PromptLang = PromptLang {
    instruction: "请分析这张图片。仅以下方的JSON格式回答，不要其他文字。",
    existing_tags: "现有标签",
    gen_prompt: "生成提示词",
    desc_hint: "图片内容描述（中文，描绘了什么，场景情况，2-3句话）",
    tags_hint: "检测到的标签（英语，Danbooru格式，最多20个）",
    quality_hint: "0-10品质评分（构图、色彩、绘画品质综合评估）",
    quality_notes_hint: "品质简评（中文）",
    palette_hint: "3-5种主要颜色（英语）",
    suggestion_hint: "提示词改进建议（中文，50字以内）",
};
const PROMPT_KO: PromptLang = PromptLang {
    instruction:
        "이 이미지를 분석해 주세요. 아래 JSON 형식으로만 응답하고 다른 텍스트는 포함하지 마세요.",
    existing_tags: "기존 태그",
    gen_prompt: "생성 프롬프트",
    desc_hint: "이미지 내용 설명 (한국어, 무엇이 묘사되었는지, 장면 상황을 2-3문장으로)",
    tags_hint: "감지된 태그 (영어, Danbooru 형식, 최대 20개)",
    quality_hint: "0-10 품질 점수 (구도, 색채, 그림 품질 종합 평가)",
    quality_notes_hint: "품질에 대한 짧은 코멘트 (한국어)",
    palette_hint: "주요 3-5색 (영어)",
    suggestion_hint: "프롬프트 개선 제안 (한국어, 50자 이내)",
};

const SIMPLE_JA: SimplePromptLang = SimplePromptLang { instruction: "この画像の色彩と構図だけを分析してください。以下のJSON形式で回答してください。他のテキストは不要です。", palette_hint: "主要な3-5色（英語）", comp_hint: "構図の詳細な説明（日本語、ライティング・配置・視線誘導を含む、2-3文）", mood_hint: "画像全体の雰囲気（日本語、1文）" };
const SIMPLE_EN: SimplePromptLang = SimplePromptLang { instruction: "Analyze ONLY the color palette and composition of this image. Respond with JSON below, no other text.", palette_hint: "3-5 dominant colors (English)", comp_hint: "Detailed composition description (English, lighting, placement, visual flow, 2-3 sentences)", mood_hint: "Overall mood of the image (English, 1 sentence)" };
const SIMPLE_ZH: SimplePromptLang = SimplePromptLang {
    instruction: "仅分析这张图片的色彩和构图。以下方的JSON格式回答，不要其他文字。",
    palette_hint: "3-5种主要颜色（英语）",
    comp_hint: "构图详细描述（中文，光线、布局、视觉引导，2-3句话）",
    mood_hint: "图片整体氛围（中文，1句话）",
};
const SIMPLE_KO: SimplePromptLang = SimplePromptLang {
    instruction: "이 이미지의 색채와 구도만 분석해 주세요. 아래 JSON 형식으로만 응답하세요.",
    palette_hint: "주요 3-5색 (영어)",
    comp_hint: "구도 상세 설명 (한국어, 조명, 배치, 시선 유도, 2-3문장)",
    mood_hint: "이미지 전체 분위기 (한국어, 1문장)",
};

const TRENDS_JA: TrendsLang = TrendsLang { instruction: "以下はAI画像生成のプロンプト{count}件です。傾向を分析して以下のJSON形式で回答してください。", prompts_label: "プロンプト", freq_tags: "よく使われるタグTOP10", style_tendency: "全体的なスタイルの傾向（日本語）", strengths: "プロンプトの強み（日本語）", weaknesses: "改善可能な点（日本語）", recommendations: "具体的な改善提案3-5個（日本語）", unexplored: "試していなさそうなテーマや手法3-5個" };
const TRENDS_EN: TrendsLang = TrendsLang { instruction: "Below are {count} AI image generation prompts. Analyze the trends and respond in the JSON format below.", prompts_label: "Prompts", freq_tags: "Top 10 frequently used tags", style_tendency: "Overall style tendency (English)", strengths: "Prompt strengths (English)", weaknesses: "Areas for improvement (English)", recommendations: "3-5 specific improvement suggestions (English)", unexplored: "3-5 unexplored themes or techniques" };
const TRENDS_ZH: TrendsLang = TrendsLang {
    instruction: "以下是{count}条AI图像生成提示词。请分析趋势并以下方JSON格式回答。",
    prompts_label: "提示词",
    freq_tags: "最常用标签TOP10",
    style_tendency: "整体风格倾向（中文）",
    strengths: "提示词的优点（中文）",
    weaknesses: "可改进之处（中文）",
    recommendations: "3-5个具体改进建议（中文）",
    unexplored: "尚未尝试的主题或手法3-5个",
};
const TRENDS_KO: TrendsLang = TrendsLang { instruction: "아래는 AI 이미지 생성 프롬프트 {count}건입니다. 트렌드를 분석하고 아래 JSON 형식으로 응답해 주세요.", prompts_label: "프롬프트", freq_tags: "자주 사용되는 태그 TOP10", style_tendency: "전체적인 스타일 경향 (한국어)", strengths: "프롬프트의 장점 (한국어)", weaknesses: "개선 가능한 점 (한국어)", recommendations: "구체적인 개선 제안 3-5개 (한국어)", unexplored: "시도하지 않은 테마나 기법 3-5개" };

fn prompt_lang(language: &str) -> &'static PromptLang {
    match language {
        "ja" => &PROMPT_JA,
        "zh" => &PROMPT_ZH,
        "ko" => &PROMPT_KO,
        _ => &PROMPT_EN,
    }
}
fn simple_lang(language: &str) -> &'static SimplePromptLang {
    match language {
        "ja" => &SIMPLE_JA,
        "zh" => &SIMPLE_ZH,
        "ko" => &SIMPLE_KO,
        _ => &SIMPLE_EN,
    }
}
fn trends_lang(language: &str) -> &'static TrendsLang {
    match language {
        "ja" => &TRENDS_JA,
        "zh" => &TRENDS_ZH,
        "ko" => &TRENDS_KO,
        _ => &TRENDS_EN,
    }
}

pub fn get_system_prompt(language: &str, _mode: AnalyzeMode) -> String {
    match language {
        "ja" => "あなたは画像分析の専門家です。回答は必ずJSON形式で、description, quality_notes, prompt_suggestion の値は必ず日本語で記述してください。英語で回答してはいけません。タグと色名のみ英語です。",
        "zh" => "你是图像分析专家。回答必须为JSON格式，description、quality_notes、prompt_suggestion 的值必须用中文。不要用英文回答。只有标签和颜色名使用英文。",
        "ko" => "당신은 이미지 분석 전문가입니다. 반드시 JSON 형식으로 응답하고, description, quality_notes, prompt_suggestion 값은 반드시 한국어로 작성하세요. 영어로 응답하지 마세요. 태그와 색상명만 영어입니다.",
        _ => "You are an image analysis expert. Respond ONLY in JSON. All text values (description, quality_notes, prompt_suggestion) MUST be in English.",
    }.to_string()
}

pub fn build_image_prompt(
    existing_tags: &[String],
    existing_prompt: Option<&str>,
    language: &str,
    mode: AnalyzeMode,
) -> String {
    if mode == AnalyzeMode::Simple {
        return build_simple_prompt(language);
    }
    if mode == AnalyzeMode::Ocr {
        if let Some(existing) = existing_prompt {
            return existing.to_string();
        }
    }
    let lang = prompt_lang(language);
    let mut context = String::new();
    if !existing_tags.is_empty() {
        context.push_str(&format!(
            "\n{}: {}",
            lang.existing_tags,
            existing_tags
                .iter()
                .take(30)
                .map(String::as_str)
                .collect::<Vec<_>>()
                .join(", ")
        ));
    }
    if let Some(prompt) = existing_prompt {
        context.push_str(&format!(
            "\n{}: {}",
            lang.gen_prompt,
            prompt.chars().take(500).collect::<String>()
        ));
    }
    let reminder = match language {
        "ja" => {
            "\n\n重要: description, quality_notes, prompt_suggestion は必ず日本語で書いてください。"
        }
        "zh" => "\n\n重要: description, quality_notes, prompt_suggestion 必须用中文。",
        "ko" => {
            "\n\n중요: description, quality_notes, prompt_suggestion은 반드시 한국어로 작성하세요."
        }
        _ => "",
    };
    format!("{}\n{}{}\n\n{{\n  \"description\": \"{}\",\n  \"tags\": [\"{}\"],\n  \"quality_score\": {},\n  \"quality_notes\": \"{}\",\n  \"style\": \"anime/realistic/sketch/watercolor/pixel_art/3d_render\",\n  \"composition\": \"portrait/full_body/close_up/landscape/group/action_pose\",\n  \"mood\": \"cheerful/dark/serene/dynamic/romantic/mysterious\",\n  \"color_palette\": [\"{}\"],\n  \"prompt_suggestion\": \"{}\"\n}}", lang.instruction, context, reminder, lang.desc_hint, lang.tags_hint, lang.quality_hint, lang.quality_notes_hint, lang.palette_hint, lang.suggestion_hint)
}

fn build_simple_prompt(language: &str) -> String {
    let lang = simple_lang(language);
    format!("{}\n\n{{\n  \"color_palette\": [\"{}\"],\n  \"composition\": \"{}\",\n  \"mood\": \"{}\"\n}}", lang.instruction, lang.palette_hint, lang.comp_hint, lang.mood_hint)
}

pub fn build_trends_prompt(prompt_texts: &[String], language: &str) -> String {
    let lang = trends_lang(language);
    let prompts = prompt_texts
        .iter()
        .take(30)
        .map(|text| format!("- {text}"))
        .collect::<Vec<_>>()
        .join("\n");
    format!("{}\n\n{}:\n{}\n\n{{\n  \"frequent_tags\": [\"{}\"],\n  \"style_tendency\": \"{}\",\n  \"strengths\": \"{}\",\n  \"weaknesses\": \"{}\",\n  \"recommendations\": [\"{}\"],\n  \"unexplored\": [\"{}\"]\n}}", lang.instruction.replace("{count}", &prompt_texts.len().to_string()), lang.prompts_label, prompts, lang.freq_tags, lang.style_tendency, lang.strengths, lang.weaknesses, lang.recommendations, lang.unexplored)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::process::Command;

    #[test]
    fn python_golden_outputs_match_all_languages() {
        let source = format!(
            r#"import importlib.util, json
spec = importlib.util.spec_from_file_location("payload", r"{}")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(json.dumps({{lang: {{
  "image_empty": module.build_image_prompt(None, None, language=lang, mode="full"),
  "image_context": module.build_image_prompt(["tag1", "tag2"], "prompt text", language=lang, mode="full"),
  "simple": module.build_image_prompt(None, None, language=lang, mode="simple"),
  "ocr": module.build_image_prompt(None, "OCR text", language=lang, mode="ocr"),
  "system": module.get_system_prompt(lang),
  "trends_empty": module.build_trends_prompt([], lang),
  "trends_context": module.build_trends_prompt(["one", "two"], lang),
}} for lang in ("ja", "en", "zh", "ko")}}, ensure_ascii=False))"#,
            std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("../../extensions/builtin_analysis/core_impl/engines_claude_payload.py")
                .display()
        );
        let output = Command::new("python3")
            .args(["-c", &source])
            .output()
            .unwrap();
        assert!(
            output.status.success(),
            "{}",
            String::from_utf8_lossy(&output.stderr)
        );
        let golden: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
        let tags = vec!["tag1".to_string(), "tag2".to_string()];
        let prompts = vec!["one".to_string(), "two".to_string()];
        for language in ["ja", "en", "zh", "ko"] {
            let expected = &golden[language];
            for (actual, key) in [
                (
                    build_image_prompt(&[], None, language, AnalyzeMode::Full),
                    "image_empty",
                ),
                (
                    build_image_prompt(&tags, Some("prompt text"), language, AnalyzeMode::Full),
                    "image_context",
                ),
                (
                    build_image_prompt(&[], None, language, AnalyzeMode::Simple),
                    "simple",
                ),
                (
                    build_image_prompt(&[], Some("OCR text"), language, AnalyzeMode::Ocr),
                    "ocr",
                ),
                (get_system_prompt(language, AnalyzeMode::Full), "system"),
                (build_trends_prompt(&[], language), "trends_empty"),
                (build_trends_prompt(&prompts, language), "trends_context"),
            ] {
                assert_eq!(
                    actual.as_bytes(),
                    expected[key].as_str().unwrap().as_bytes(),
                    "{language} {key}"
                );
            }
        }
    }

    #[test]
    fn python_golden_modes_and_fallback_match() {
        assert_eq!(
            build_image_prompt(&[], Some("OCR text"), "en", AnalyzeMode::Ocr),
            "OCR text"
        );
        assert!(
            build_image_prompt(&[], None, "en", AnalyzeMode::Simple).starts_with("Analyze ONLY")
        );
        assert_eq!(
            get_system_prompt("unknown", AnalyzeMode::Full),
            get_system_prompt("en", AnalyzeMode::Full)
        );
    }
}
