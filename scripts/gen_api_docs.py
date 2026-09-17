"""Generate API documentation from route source files.

Parses routes/ and extensions/ directories using AST (no imports),
extracts endpoint definitions, and writes docs/{lang}/api/all-endpoints.md
for all 11 supported languages.

Usage:
    uv run python scripts/gen_api_docs.py            # generate all 11 languages
    uv run python scripts/gen_api_docs.py --lang ja  # single language
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
NATIVE_ONLY_ENDPOINTS = ROOT / "docs" / "development" / "native-only-endpoints.yaml"

SUPPORTED_LANGS = ["ja", "en", "zh-cn", "zh-tw", "ko", "de", "es", "fr", "it", "pt", "ru"]

# URL prefix → canonical English category key (checked in order, first match wins)
CATEGORIES: list[tuple[str, str]] = [
    ("/api/search", "Search"),
    ("/api/suggest", "Search"),
    ("/api/server-info", "Search"),
    ("/api/file", "Files"),
    ("/api/thumbnail", "Files"),
    ("/api/original", "Files"),
    ("/api/convert", "Files"),
    ("/api/preview", "Files"),
    ("/api/container-thumb", "Files"),
    ("/api/groups", "Files"),
    ("/api/group-", "Files"),
    ("/api/scan-root", "Scan"),
    ("/api/scanned-root", "Scan"),
    ("/api/scan", "Scan"),
    ("/api/tags", "Tags"),
    ("/api/ratings", "Ratings & Favorites"),
    ("/api/favorites", "Ratings & Favorites"),
    ("/api/annotations", "Annotations"),
    ("/api/collections", "Collections"),
    ("/api/wd-tagger", "WD-Tagger"),
    ("/api/tagger-servers", "WD-Tagger"),
    ("/api/analysis", "AI Analysis"),
    ("/api/ocr", "AI Analysis"),
    ("/api/video-analysis", "AI Analysis"),
    ("/api/speech", "AI Analysis"),
    ("/api/agent", "Agents"),
    ("/api/llm_router", "LLM Router"),
    ("/api/bridge", "Bridge"),
    ("/sdapi/v1", "Bridge"),
    ("/api/comfy", "Bridge"),
    ("/api/nai", "Bridge"),
    ("/api/gateway", "Bridge"),
    ("/api/settings", "Settings"),
    ("/api/profiles", "Settings"),
    ("/api/connections", "Settings"),
    ("/api/extensions", "Extensions"),
    ("/api/ui", "Extensions"),
    ("/api/admin", "Administration"),
    ("/api/maintenance", "Administration"),
    ("/api/server", "Administration"),
    ("/api/fleet", "Administration"),
    ("/api/scheduler", "Administration"),
    ("/api/inspect", "Administration"),
    ("/api/help", "Administration"),
    ("/api/events", "SSE & Logs"),
    ("/api/logs", "SSE & Logs"),
    ("/api/mesh-inference", "Mesh Inference"),
    ("/api/hailo", "Hailo"),
    ("/api/inference", "Hailo"),
    ("/api/hailo-tagger", "WD-Tagger"),
    ("/api/mdns", "LAN Share"),
    ("/api/lan", "LAN Share"),
    ("/api/share", "LAN Share"),
    ("/api/stats", "Stats"),
    ("/api/monthly-report", "Stats"),
    ("/api/trophy", "Stats"),
    ("/api/dnd", "Files"),
    ("/api/open-folder", "Files"),
    ("/api/outputs", "Files"),
    ("/api/folders", "Files"),
    ("/api/prompts", "Prompt Library"),
    ("/api/chat", "Chat"),
    ("/api/conversations", "Chat"),
    ("/api/stream", "SNS & Streams"),
    ("/api/sns", "SNS & Streams"),
    ("/api/webhooks", "SNS & Streams"),
    ("/api/github", "SNS & Streams"),
    ("/api/sweeps", "Bridge"),
]

DEFAULT_CATEGORY = "MCP & Internal API"

# Per-language display labels for each canonical category key
CATEGORY_LABELS: dict[str, dict[str, str]] = {
    "ja": {
        "Search": "検索",
        "Files": "ファイル",
        "Scan": "スキャン",
        "Tags": "タグ",
        "Ratings & Favorites": "レーティング・お気に入り",
        "Annotations": "アノテーション",
        "Collections": "コレクション",
        "WD-Tagger": "WD-Tagger",
        "AI Analysis": "AI 分析",
        "Agents": "エージェント",
        "LLM Router": "LLM ルータ",
        "Bridge": "Bridge",
        "Settings": "設定",
        "Extensions": "拡張機能",
        "Administration": "管理",
        "SSE & Logs": "SSE・ログ",
        "Mesh Inference": "メッシュ推論",
        "Hailo": "Hailo",
        "LAN Share": "LAN 共有",
        "Stats": "統計",
        "Prompt Library": "プロンプト管理",
        "Chat": "チャット",
        "SNS & Streams": "SNS・ストリーム",
        "MCP & Internal API": "MCP・内部 API",
    },
    "en": {
        "Search": "Search",
        "Files": "Files",
        "Scan": "Scan",
        "Tags": "Tags",
        "Ratings & Favorites": "Ratings & Favorites",
        "Annotations": "Annotations",
        "Collections": "Collections",
        "WD-Tagger": "WD-Tagger",
        "AI Analysis": "AI Analysis",
        "Agents": "Agents",
        "LLM Router": "LLM Router",
        "Bridge": "Bridge",
        "Settings": "Settings",
        "Extensions": "Extensions",
        "Administration": "Administration",
        "SSE & Logs": "SSE & Logs",
        "Mesh Inference": "Mesh Inference",
        "Hailo": "Hailo",
        "LAN Share": "LAN Share",
        "Stats": "Stats",
        "Prompt Library": "Prompt Library",
        "Chat": "Chat",
        "SNS & Streams": "SNS & Streams",
        "MCP & Internal API": "MCP & Internal API",
    },
    "zh-cn": {
        "Search": "搜索",
        "Files": "文件",
        "Scan": "扫描",
        "Tags": "标签",
        "Ratings & Favorites": "评分与收藏",
        "Annotations": "注释",
        "Collections": "收藏集",
        "WD-Tagger": "WD-Tagger",
        "AI Analysis": "AI分析",
        "Agents": "代理",
        "LLM Router": "LLM Router",
        "Bridge": "Bridge",
        "Settings": "设置",
        "Extensions": "扩展",
        "Administration": "管理",
        "SSE & Logs": "SSE & 日志",
        "Mesh Inference": "网格推理",
        "Hailo": "Hailo",
        "LAN Share": "LAN共享",
        "Stats": "统计",
        "Prompt Library": "提示词库",
        "Chat": "聊天",
        "SNS & Streams": "社交网络与流",
        "MCP & Internal API": "MCP & 内部API",
    },
    "zh-tw": {
        "Search": "搜尋",
        "Files": "檔案",
        "Scan": "掃描",
        "Tags": "標籤",
        "Ratings & Favorites": "評分與收藏",
        "Annotations": "註釋",
        "Collections": "收藏集",
        "WD-Tagger": "WD-Tagger",
        "AI Analysis": "AI分析",
        "Agents": "代理",
        "LLM Router": "LLM Router",
        "Bridge": "Bridge",
        "Settings": "設定",
        "Extensions": "擴充功能",
        "Administration": "管理",
        "SSE & Logs": "SSE & 日誌",
        "Mesh Inference": "網格推論",
        "Hailo": "Hailo",
        "LAN Share": "LAN共享",
        "Stats": "統計",
        "Prompt Library": "提示詞庫",
        "Chat": "聊天",
        "SNS & Streams": "社交網路與串流",
        "MCP & Internal API": "MCP & 內部API",
    },
    "ko": {
        "Search": "검색",
        "Files": "파일",
        "Scan": "스캔",
        "Tags": "태그",
        "Ratings & Favorites": "평점 및 즐겨찾기",
        "Annotations": "주석",
        "Collections": "컬렉션",
        "WD-Tagger": "WD-Tagger",
        "AI Analysis": "AI 분석",
        "Agents": "에이전트",
        "LLM Router": "LLM Router",
        "Bridge": "Bridge",
        "Settings": "설정",
        "Extensions": "확장 기능",
        "Administration": "관리",
        "SSE & Logs": "SSE 및 로그",
        "Mesh Inference": "메시 추론",
        "Hailo": "Hailo",
        "LAN Share": "LAN 공유",
        "Stats": "통계",
        "Prompt Library": "프롬프트 라이브러리",
        "Chat": "채팅",
        "SNS & Streams": "SNS 및 스트림",
        "MCP & Internal API": "MCP 및 내부 API",
    },
    "de": {
        "Search": "Suche",
        "Files": "Dateien",
        "Scan": "Scan",
        "Tags": "Tags",
        "Ratings & Favorites": "Bewertungen & Favoriten",
        "Annotations": "Anmerkungen",
        "Collections": "Sammlungen",
        "WD-Tagger": "WD-Tagger",
        "AI Analysis": "KI-Analyse",
        "Agents": "Agenten",
        "LLM Router": "LLM Router",
        "Bridge": "Bridge",
        "Settings": "Einstellungen",
        "Extensions": "Erweiterungen",
        "Administration": "Verwaltung",
        "SSE & Logs": "SSE & Protokolle",
        "Mesh Inference": "Mesh-Inferenz",
        "Hailo": "Hailo",
        "LAN Share": "LAN-Freigabe",
        "Stats": "Statistiken",
        "Prompt Library": "Prompt-Bibliothek",
        "Chat": "Chat",
        "SNS & Streams": "SNS & Streams",
        "MCP & Internal API": "MCP & Interne API",
    },
    "es": {
        "Search": "Búsqueda",
        "Files": "Archivos",
        "Scan": "Escanear",
        "Tags": "Etiquetas",
        "Ratings & Favorites": "Calificaciones y Favoritos",
        "Annotations": "Anotaciones",
        "Collections": "Colecciones",
        "WD-Tagger": "WD-Tagger",
        "AI Analysis": "Análisis de IA",
        "Agents": "Agentes",
        "LLM Router": "LLM Router",
        "Bridge": "Bridge",
        "Settings": "Configuración",
        "Extensions": "Extensiones",
        "Administration": "Administración",
        "SSE & Logs": "SSE y Registros",
        "Mesh Inference": "Inferencia de Malla",
        "Hailo": "Hailo",
        "LAN Share": "Compartición LAN",
        "Stats": "Estadísticas",
        "Prompt Library": "Biblioteca de Prompts",
        "Chat": "Chat",
        "SNS & Streams": "SNS y Transmisiones",
        "MCP & Internal API": "MCP e API Interna",
    },
    "fr": {
        "Search": "Recherche",
        "Files": "Fichiers",
        "Scan": "Analyse",
        "Tags": "Tags",
        "Ratings & Favorites": "Évaluations & Favoris",
        "Annotations": "Annotations",
        "Collections": "Collections",
        "WD-Tagger": "WD-Tagger",
        "AI Analysis": "Analyse IA",
        "Agents": "Agents",
        "LLM Router": "LLM Router",
        "Bridge": "Bridge",
        "Settings": "Paramètres",
        "Extensions": "Extensions",
        "Administration": "Administration",
        "SSE & Logs": "SSE & Journaux",
        "Mesh Inference": "Inférence Mesh",
        "Hailo": "Hailo",
        "LAN Share": "Partage LAN",
        "Stats": "Statistiques",
        "Prompt Library": "Bibliothèque de Prompts",
        "Chat": "Chat",
        "SNS & Streams": "SNS & Flux",
        "MCP & Internal API": "MCP et API Interne",
    },
    "it": {
        "Search": "Ricerca",
        "Files": "File",
        "Scan": "Scansione",
        "Tags": "Tag",
        "Ratings & Favorites": "Valutazioni e Preferiti",
        "Annotations": "Annotazioni",
        "Collections": "Collezioni",
        "WD-Tagger": "WD-Tagger",
        "AI Analysis": "Analisi IA",
        "Agents": "Agenti",
        "LLM Router": "LLM Router",
        "Bridge": "Bridge",
        "Settings": "Impostazioni",
        "Extensions": "Estensioni",
        "Administration": "Amministrazione",
        "SSE & Logs": "SSE & Log",
        "Mesh Inference": "Inferenza Mesh",
        "Hailo": "Hailo",
        "LAN Share": "Condivisione LAN",
        "Stats": "Statistiche",
        "Prompt Library": "Libreria di Prompt",
        "Chat": "Chat",
        "SNS & Streams": "SNS e Flussi",
        "MCP & Internal API": "MCP e API Interna",
    },
    "pt": {
        "Search": "Pesquisa",
        "Files": "Arquivos",
        "Scan": "Varredura",
        "Tags": "Tags",
        "Ratings & Favorites": "Classificações e Favoritos",
        "Annotations": "Anotações",
        "Collections": "Coleções",
        "WD-Tagger": "WD-Tagger",
        "AI Analysis": "Análise de IA",
        "Agents": "Agentes",
        "LLM Router": "LLM Router",
        "Bridge": "Bridge",
        "Settings": "Configurações",
        "Extensions": "Extensões",
        "Administration": "Administração",
        "SSE & Logs": "SSE e Logs",
        "Mesh Inference": "Inferência em Mesh",
        "Hailo": "Hailo",
        "LAN Share": "Compartilhamento LAN",
        "Stats": "Estatísticas",
        "Prompt Library": "Biblioteca de Prompts",
        "Chat": "Bate-papo",
        "SNS & Streams": "SNS e Fluxos",
        "MCP & Internal API": "MCP e API Interna",
    },
    "ru": {
        "Search": "Поиск",
        "Files": "Файлы",
        "Scan": "Сканирование",
        "Tags": "Теги",
        "Ratings & Favorites": "Рейтинги и Избранное",
        "Annotations": "Аннотации",
        "Collections": "Коллекции",
        "WD-Tagger": "WD-Tagger",
        "AI Analysis": "Анализ ИИ",
        "Agents": "Агенты",
        "LLM Router": "LLM Router",
        "Bridge": "Bridge",
        "Settings": "Параметры",
        "Extensions": "Расширения",
        "Administration": "Администрирование",
        "SSE & Logs": "SSE и логи",
        "Mesh Inference": "Сетевой вывод",
        "Hailo": "Hailo",
        "LAN Share": "Общий доступ LAN",
        "Stats": "Статистика",
        "Prompt Library": "Библиотека промптов",
        "Chat": "Чат",
        "SNS & Streams": "SNS и потоки",
        "MCP & Internal API": "MCP и внутренний API",
    },
}

UI_STRINGS: dict[str, dict[str, str]] = {
    "ja": {
        "title": "API エンドポイント一覧（自動生成）",
        "auto_gen_notice": "このファイルは `scripts/gen_api_docs.py` で自動生成されます。手動編集しないでください。",
        "source_note": "生成元: `routes/`, `extensions/`, `core/lan_share/`",
        "total": "**合計**: {n} エンドポイント",
        "toc_header": "## 目次",
        "toc_item_suffix": "({n}件)",
        "table_method": "メソッド",
        "table_path": "パス",
        "table_desc": "説明",
        "table_file": "ファイル",
    },
    "en": {
        "title": "API Endpoint Reference (auto-generated)",
        "auto_gen_notice": "This file is auto-generated by `scripts/gen_api_docs.py`. Do not edit manually.",
        "source_note": "Sources: `routes/`, `extensions/`, `core/lan_share/`",
        "total": "**Total**: {n} endpoints",
        "toc_header": "## Table of Contents",
        "toc_item_suffix": "({n} entries)",
        "table_method": "Method",
        "table_path": "Path",
        "table_desc": "Description",
        "table_file": "File",
    },
    "zh-cn": {
        "title": "API端点参考（自动生成）",
        "auto_gen_notice": "此文件由 `scripts/gen_api_docs.py` 自动生成。请勿手动编辑。",
        "source_note": "来源：`routes/`, `extensions/`, `core/lan_share/`",
        "total": "**总计**：{n} 个端点",
        "toc_header": "## 目录",
        "toc_item_suffix": "（{n} 项）",
        "table_method": "方法",
        "table_path": "路径",
        "table_desc": "描述",
        "table_file": "文件",
    },
    "zh-tw": {
        "title": "API端點參考（自動生成）",
        "auto_gen_notice": "此檔案由 `scripts/gen_api_docs.py` 自動生成。請勿手動編輯。",
        "source_note": "來源：`routes/`, `extensions/`, `core/lan_share/`",
        "total": "**總計**：{n} 個端點",
        "toc_header": "## 目錄",
        "toc_item_suffix": "（{n} 項）",
        "table_method": "方法",
        "table_path": "路徑",
        "table_desc": "描述",
        "table_file": "檔案",
    },
    "ko": {
        "title": "API 엔드포인트 참조 (자동 생성)",
        "auto_gen_notice": "이 파일은 `scripts/gen_api_docs.py`에 의해 자동 생성됩니다. 수동으로 편집하지 마십시오.",
        "source_note": "소스: `routes/`, `extensions/`, `core/lan_share/`",
        "total": "**총**: {n} 엔드포인트",
        "toc_header": "## 목차",
        "toc_item_suffix": "({n} 항목)",
        "table_method": "메서드",
        "table_path": "경로",
        "table_desc": "설명",
        "table_file": "파일",
    },
    "de": {
        "title": "API-Endpunkt-Referenz (automatisch generiert)",
        "auto_gen_notice": "Diese Datei wird automatisch von `scripts/gen_api_docs.py` generiert. Nicht manuell bearbeiten.",
        "source_note": "Quellen: `routes/`, `extensions/`, `core/lan_share/`",
        "total": "**Gesamt**: {n} Endpunkte",
        "toc_header": "## Inhaltsverzeichnis",
        "toc_item_suffix": "({n} Einträge)",
        "table_method": "Methode",
        "table_path": "Pfad",
        "table_desc": "Beschreibung",
        "table_file": "Datei",
    },
    "es": {
        "title": "Referencia de Endpoints API (generado automáticamente)",
        "auto_gen_notice": "Este archivo se genera automáticamente mediante `scripts/gen_api_docs.py`. No edite manualmente.",
        "source_note": "Fuentes: `routes/`, `extensions/`, `core/lan_share/`",
        "total": "**Total**: {n} endpoints",
        "toc_header": "## Tabla de Contenidos",
        "toc_item_suffix": "({n} entradas)",
        "table_method": "Método",
        "table_path": "Ruta",
        "table_desc": "Descripción",
        "table_file": "Archivo",
    },
    "fr": {
        "title": "Référence des Endpoints API (généré automatiquement)",
        "auto_gen_notice": "Ce fichier est généré automatiquement par `scripts/gen_api_docs.py`. Ne pas éditer manuellement.",
        "source_note": "Sources: `routes/`, `extensions/`, `core/lan_share/`",
        "total": "**Total**: {n} endpoints",
        "toc_header": "## Table des Matières",
        "toc_item_suffix": "({n} entrées)",
        "table_method": "Méthode",
        "table_path": "Chemin",
        "table_desc": "Description",
        "table_file": "Fichier",
    },
    "it": {
        "title": "Riferimento Endpoint API (generato automaticamente)",
        "auto_gen_notice": "Questo file è generato automaticamente da `scripts/gen_api_docs.py`. Non modificare manualmente.",
        "source_note": "Fonti: `routes/`, `extensions/`, `core/lan_share/`",
        "total": "**Totale**: {n} endpoint",
        "toc_header": "## Indice",
        "toc_item_suffix": "({n} voci)",
        "table_method": "Metodo",
        "table_path": "Percorso",
        "table_desc": "Descrizione",
        "table_file": "File",
    },
    "pt": {
        "title": "Referência de Endpoints da API (gerado automaticamente)",
        "auto_gen_notice": "Este arquivo é gerado automaticamente por `scripts/gen_api_docs.py`. Não edite manualmente.",
        "source_note": "Fontes: `routes/`, `extensions/`, `core/lan_share/`",
        "total": "**Total**: {n} endpoints",
        "toc_header": "## Sumário",
        "toc_item_suffix": "({n} entradas)",
        "table_method": "Método",
        "table_path": "Caminho",
        "table_desc": "Descrição",
        "table_file": "Arquivo",
    },
    "ru": {
        "title": "Справочник API-эндпоинтов (автоматически сгенерирован)",
        "auto_gen_notice": "Этот файл автоматически генерируется `scripts/gen_api_docs.py`. Не редактируйте вручную.",
        "source_note": "Источники: `routes/`, `extensions/`, `core/lan_share/`",
        "total": "**Всего**: {n} эндпоинтов",
        "toc_header": "## Оглавление",
        "toc_item_suffix": "({n} позиций)",
        "table_method": "Метод",
        "table_path": "Путь",
        "table_desc": "Описание",
        "table_file": "Файл",
    },
}


@dataclass
class Endpoint:
    path: str
    methods: list[str]
    source_file: str
    docstring: str = ""
    func_name: str = ""
    category: str = ""


def _categorize(path: str) -> str:
    for prefix, label in CATEGORIES:
        if path.startswith(prefix):
            return label
    return DEFAULT_CATEGORY


def _extract_string(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _extract_methods(keywords: list[ast.keyword]) -> list[str]:
    for kw in keywords:
        if kw.arg == "methods" and isinstance(kw.value, ast.List):
            return [
                _extract_string(elt) or ""
                for elt in kw.value.elts
                if isinstance(elt, ast.Constant)
            ]
    return ["GET"]


def _get_docstring(func_node: ast.AsyncFunctionDef | ast.FunctionDef) -> str:
    if (
        func_node.body
        and isinstance(func_node.body[0], ast.Expr)
        and isinstance(func_node.body[0].value, ast.Constant)
    ):
        return str(func_node.body[0].value.value).strip().split("\n")[0]
    return ""


def _parse_file(path: Path) -> list[Endpoint]:
    """Extract endpoints from a single Python source file using AST."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    endpoints: list[Endpoint] = []
    rel = str(path.relative_to(ROOT))

    func_map: dict[str, ast.AsyncFunctionDef | ast.FunctionDef] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            func_map[node.name] = node

    for node in ast.walk(tree):
        # Pattern 1: @bp.route("/api/xxx") decorator
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            for deco in node.decorator_list:
                if not isinstance(deco, ast.Call):
                    continue
                func = deco.func
                if not (isinstance(func, ast.Attribute) and func.attr == "route"):
                    continue
                if not deco.args:
                    continue
                route_path = _extract_string(deco.args[0])
                if not route_path:
                    continue
                methods = _extract_methods(deco.keywords)
                endpoints.append(Endpoint(
                    path=route_path,
                    methods=methods,
                    source_file=rel,
                    docstring=_get_docstring(node),
                    func_name=node.name,
                ))

        # Pattern 2: bp.add_url_rule("/api/xxx", view_func=fn, methods=[...])
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            func = call.func
            if not (isinstance(func, ast.Attribute) and func.attr == "add_url_rule"):
                continue
            if not call.args:
                continue
            route_path = _extract_string(call.args[0])
            if not route_path:
                continue
            methods = _extract_methods(call.keywords)

            docstring = ""
            func_name = ""
            for kw in call.keywords:
                if kw.arg == "view_func":
                    if isinstance(kw.value, ast.Attribute):
                        func_name = kw.value.attr
                    elif isinstance(kw.value, ast.Name):
                        func_name = kw.value.id
                    if func_name in func_map:
                        docstring = _get_docstring(func_map[func_name])

            endpoints.append(Endpoint(
                path=route_path,
                methods=methods,
                source_file=rel,
                docstring=docstring,
                func_name=func_name,
            ))

    return endpoints


def collect_python_endpoints() -> list[Endpoint]:
    """Collect endpoints defined in Python routes/ and extensions/."""
    all_endpoints: list[Endpoint] = []

    search_dirs = [ROOT / "routes", ROOT / "extensions", ROOT / "core" / "lan_share"]
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for py_file in sorted(search_dir.rglob("*.py")):
            if "__pycache__" in str(py_file):
                continue
            endpoints = _parse_file(py_file)
            all_endpoints.extend(endpoints)

    seen: set[tuple[str, str]] = set()
    unique: list[Endpoint] = []
    for ep in all_endpoints:
        key = (ep.path, ",".join(sorted(ep.methods)))
        if key not in seen:
            seen.add(key)
            unique.append(ep)

    return unique


def _native_only_endpoints() -> list[Endpoint]:
    data = yaml.safe_load(NATIVE_ONLY_ENDPOINTS.read_text(encoding="utf-8")) or {}
    return [
        Endpoint(
            path=item["path"],
            methods=item["methods"],
            source_file=item["rust_module"],
            docstring=item["summary"],
            category=item["category"],
        )
        for item in data.get("endpoints", [])
    ]


def collect_endpoints() -> list[Endpoint]:
    """Collect Python and documented native-only endpoints."""
    all_endpoints = collect_python_endpoints() + _native_only_endpoints()
    seen: set[tuple[str, str]] = set()
    unique: list[Endpoint] = []
    for ep in all_endpoints:
        key = (ep.path, ",".join(sorted(ep.methods)))
        if key not in seen:
            seen.add(key)
            unique.append(ep)
    return sorted(unique, key=lambda e: (e.path, e.methods))


def _method_badge(method: str) -> str:
    labels = {"GET": "GET", "POST": "POST", "PUT": "PUT", "DELETE": "DELETE", "PATCH": "PATCH"}
    return f"`{labels.get(method, method)}`"


def render_markdown(endpoints: list[Endpoint], lang: str) -> str:
    """Generate a localised Markdown document from the endpoint list."""
    cats = CATEGORY_LABELS.get(lang, CATEGORY_LABELS["en"])
    ui = UI_STRINGS.get(lang, UI_STRINGS["en"])

    def label(key: str) -> str:
        return cats.get(key, key)

    grouped: dict[str, list[Endpoint]] = {}
    for ep in endpoints:
        cat = ep.category or _categorize(ep.path)
        grouped.setdefault(cat, []).append(ep)

    ordered_cats: list[str] = []
    seen_cats: set[str] = set()
    for _, canonical in CATEGORIES:
        if canonical not in seen_cats:
            ordered_cats.append(canonical)
            seen_cats.add(canonical)
    if DEFAULT_CATEGORY in grouped and DEFAULT_CATEGORY not in seen_cats:
        ordered_cats.append(DEFAULT_CATEGORY)

    lines: list[str] = []
    lines.append(f"# {ui['title']}")
    lines.append("")
    lines.append(f"> {ui['auto_gen_notice']}")
    lines.append(f"> {ui['source_note']}")
    lines.append("")
    lines.append(ui["total"].format(n=len(endpoints)))
    lines.append("")

    lines.append(ui["toc_header"])
    lines.append("")
    for cat in ordered_cats:
        if cat not in grouped:
            continue
        display = label(cat)
        anchor = re.sub(r"[^\w\- ]", "", display).strip().replace(" ", "-").lower()
        count = len(grouped[cat])
        suffix = ui["toc_item_suffix"].format(n=count)
        lines.append(f"- [{display}](#{anchor}) {suffix}")
    lines.append("")

    for cat in ordered_cats:
        if cat not in grouped:
            continue
        display = label(cat)
        lines.append(f"## {display}")
        lines.append("")
        m = ui["table_method"]
        p = ui["table_path"]
        d = ui["table_desc"]
        f = ui["table_file"]
        lines.append(f"| {m} | {p} | {d} | {f} |")
        lines.append("|---------|------|------|---------|")
        for ep in grouped[cat]:
            methods_str = " ".join(_method_badge(method) for method in ep.methods)
            desc = ep.docstring.replace("|", "\\|") if ep.docstring else "—"
            src = ep.source_file
            lines.append(f"| {methods_str} | `{ep.path}` | {desc} | `{src}` |")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate multilingual API endpoint docs.")
    parser.add_argument(
        "--lang",
        choices=SUPPORTED_LANGS,
        default=None,
        help="Target language (default: generate all supported languages)",
    )
    args = parser.parse_args()

    print("Collecting endpoints...", file=sys.stderr)
    endpoints = collect_endpoints()
    print(f"Found {len(endpoints)} endpoints.", file=sys.stderr)

    langs = [args.lang] if args.lang else SUPPORTED_LANGS

    for lang in langs:
        md = render_markdown(endpoints, lang)
        out_path = ROOT / "docs" / lang / "api" / "all-endpoints.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(md, encoding="utf-8")
        print(f"Written: {out_path}", file=sys.stderr)

    if not args.lang:
        print(f"Done. Generated {len(langs)} language versions.", file=sys.stderr)


if __name__ == "__main__":
    main()
