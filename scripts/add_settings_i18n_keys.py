"""Add missing settings i18n keys to all language files."""
import json
from pathlib import Path

I18N_DIR = Path("ui/default/static/i18n")

# Keys to add per language
TRANSLATIONS = {
    "en": {
        "settings.cat.server": "Server",
        "settings.cat.scan": "Scan",
        "settings.cat.tagging": "Tagging",
        "settings.cat.appearance": "Appearance",
        "settings.cat.auth": "Auth",
        "settings.cat.dev": "Dev",
        "settings.save": "Save",
        "settings.unsaved_hint": "Unsaved changes",
    },
    "ja": {
        "settings.cat.server": "サーバー",
        "settings.cat.scan": "スキャン",
        "settings.cat.tagging": "タグ付け",
        "settings.cat.appearance": "外観",
        "settings.cat.auth": "認証",
        "settings.cat.dev": "開発",
        "settings.save": "保存",
        "settings.unsaved_hint": "未保存の変更があります",
    },
    "de": {
        "settings.cat.server": "Server",
        "settings.cat.scan": "Scan",
        "settings.cat.tagging": "Tagging",
        "settings.cat.appearance": "Aussehen",
        "settings.cat.auth": "Authentifizierung",
        "settings.cat.dev": "Entwicklung",
        "settings.save": "Speichern",
        "settings.unsaved_hint": "Nicht gespeicherte Änderungen",
    },
    "es": {
        "settings.cat.server": "Servidor",
        "settings.cat.scan": "Escaneo",
        "settings.cat.tagging": "Etiquetado",
        "settings.cat.appearance": "Apariencia",
        "settings.cat.auth": "Autenticación",
        "settings.cat.dev": "Desarrollo",
        "settings.save": "Guardar",
        "settings.unsaved_hint": "Cambios no guardados",
    },
    "fr": {
        "settings.cat.server": "Serveur",
        "settings.cat.scan": "Scan",
        "settings.cat.tagging": "Étiquetage",
        "settings.cat.appearance": "Apparence",
        "settings.cat.auth": "Authentification",
        "settings.cat.dev": "Développement",
        "settings.save": "Enregistrer",
        "settings.unsaved_hint": "Modifications non enregistrées",
    },
    "it": {
        "settings.cat.server": "Server",
        "settings.cat.scan": "Scansione",
        "settings.cat.tagging": "Tagging",
        "settings.cat.appearance": "Aspetto",
        "settings.cat.auth": "Autenticazione",
        "settings.cat.dev": "Sviluppo",
        "settings.save": "Salva",
        "settings.unsaved_hint": "Modifiche non salvate",
    },
    "ko": {
        "settings.cat.server": "서버",
        "settings.cat.scan": "스캔",
        "settings.cat.tagging": "태깅",
        "settings.cat.appearance": "외관",
        "settings.cat.auth": "인증",
        "settings.cat.dev": "개발",
        "settings.save": "저장",
        "settings.unsaved_hint": "저장되지 않은 변경사항",
    },
    "pt": {
        "settings.cat.server": "Servidor",
        "settings.cat.scan": "Varredura",
        "settings.cat.tagging": "Marcação",
        "settings.cat.appearance": "Aparência",
        "settings.cat.auth": "Autenticação",
        "settings.cat.dev": "Desenvolvimento",
        "settings.save": "Salvar",
        "settings.unsaved_hint": "Alterações não salvas",
    },
    "ru": {
        "settings.cat.server": "Сервер",
        "settings.cat.scan": "Сканирование",
        "settings.cat.tagging": "Теггирование",
        "settings.cat.appearance": "Внешний вид",
        "settings.cat.auth": "Авторизация",
        "settings.cat.dev": "Разработка",
        "settings.save": "Сохранить",
        "settings.unsaved_hint": "Несохранённые изменения",
    },
    "zh-cn": {
        "settings.cat.server": "服务器",
        "settings.cat.scan": "扫描",
        "settings.cat.tagging": "标签",
        "settings.cat.appearance": "外观",
        "settings.cat.auth": "认证",
        "settings.cat.dev": "开发",
        "settings.save": "保存",
        "settings.unsaved_hint": "有未保存的更改",
    },
    "zh-tw": {
        "settings.cat.server": "伺服器",
        "settings.cat.scan": "掃描",
        "settings.cat.tagging": "標籤",
        "settings.cat.appearance": "外觀",
        "settings.cat.auth": "認證",
        "settings.cat.dev": "開發",
        "settings.save": "儲存",
        "settings.unsaved_hint": "有未儲存的變更",
    },
}

for lang, new_keys in TRANSLATIONS.items():
    path = I18N_DIR / f"{lang}.json"
    if not path.exists():
        print(f"SKIP {lang} (not found)")
        continue
    data = json.loads(path.read_text(encoding="utf-8"))
    added = []
    for key, val in new_keys.items():
        if key not in data:
            data[key] = val
            added.append(key)
    if added:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"  {lang}: added {len(added)} keys")
    else:
        print(f"  {lang}: already up-to-date")

print("Done.")
