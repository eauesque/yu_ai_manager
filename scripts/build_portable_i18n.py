"""i18n helpers for the portable build script."""

from __future__ import annotations

import locale
import os


def detect_lang() -> str:
    """Detect UI language from environment."""
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(var, "")
        if val:
            lang = val.split(".")[0].split("@")[0]
            if lang.startswith("ja"):
                return "ja"
            if lang.startswith("ko"):
                return "ko"
            if lang in ("zh_TW", "zh_HK"):
                return "zh_TW"
            if lang in ("zh_CN", "zh_SG"):
                return "zh_CN"
            if lang.startswith("zh"):
                return "zh_CN"
            return "en"
    try:
        sys_locale = locale.getdefaultlocale()[0] or ""
    except Exception:
        sys_locale = ""
    if sys_locale.startswith("ja"):
        return "ja"
    if sys_locale.startswith("ko"):
        return "ko"
    if "TW" in sys_locale or "HK" in sys_locale:
        return "zh_TW"
    if sys_locale.startswith("zh"):
        return "zh_CN"
    return "en"


MESSAGES = {
    "dl_python": {"ja": "[BUILD] Python {ver} Embeddable をダウンロード中...", "en": "[BUILD] Downloading Python {ver} Embeddable...", "ko": "[BUILD] Python {ver} Embeddable 다운로드 중...", "zh_TW": "[BUILD] 正在下載 Python {ver} Embeddable...", "zh_CN": "[BUILD] 正在下载 Python {ver} Embeddable..."},
    "dl_url": {"ja": "  URL: {url}", "en": "  URL: {url}", "ko": "  URL: {url}", "zh_TW": "  URL: {url}", "zh_CN": "  URL: {url}"},
    "dl_done": {"ja": "[BUILD] Python {ver} 展開完了 ({size} MB)", "en": "[BUILD] Python {ver} extracted ({size} MB)", "ko": "[BUILD] Python {ver} 압축 해제 완료 ({size} MB)", "zh_TW": "[BUILD] Python {ver} 解壓完成 ({size} MB)", "zh_CN": "[BUILD] Python {ver} 解压完成 ({size} MB)"},
    "install_pip": {"ja": "[BUILD] pip をインストール中...", "en": "[BUILD] Installing pip...", "ko": "[BUILD] pip 설치 중...", "zh_TW": "[BUILD] 正在安裝 pip...", "zh_CN": "[BUILD] 正在安装 pip..."},
    "install_pip_done": {"ja": "[BUILD] pip インストール完了", "en": "[BUILD] pip installation complete", "ko": "[BUILD] pip 설치 완료", "zh_TW": "[BUILD] pip 安裝完成", "zh_CN": "[BUILD] pip 安装完成"},
    "pth_not_found": {"ja": "[WARN] _pth ファイルが見つかりません", "en": "[WARN] _pth file not found", "ko": "[WARN] _pth 파일을 찾을 수 없습니다", "zh_TW": "[WARN] 找不到 _pth 檔案", "zh_CN": "[WARN] 找不到 _pth 文件"},
    "pth_edited": {"ja": "[BUILD] {name} を編集: site-packages 有効化", "en": "[BUILD] Edited {name}: site-packages enabled", "ko": "[BUILD] {name} 편집: site-packages 활성화", "zh_TW": "[BUILD] 已編輯 {name}: 啟用 site-packages", "zh_CN": "[BUILD] 已编辑 {name}: 启用 site-packages"},
    "install_deps": {"ja": "[BUILD] 依存パッケージをインストール中...", "en": "[BUILD] Installing dependencies...", "ko": "[BUILD] 의존성 패키지 설치 중...", "zh_TW": "[BUILD] 正在安裝依賴套件...", "zh_CN": "[BUILD] 正在安装依赖包..."},
    "install_deps_done": {"ja": "[BUILD] 依存パッケージインストール完了", "en": "[BUILD] Dependencies installed", "ko": "[BUILD] 의존성 패키지 설치 완료", "zh_TW": "[BUILD] 依賴套件安裝完成", "zh_CN": "[BUILD] 依赖包安装完成"},
    "cleanup_done": {"ja": "[BUILD] 不要ファイル {n} 件削除", "en": "[BUILD] Removed {n} unnecessary files", "ko": "[BUILD] 불필요한 파일 {n}개 삭제", "zh_TW": "[BUILD] 已刪除 {n} 個不必要的檔案", "zh_CN": "[BUILD] 已删除 {n} 个不必要的文件"},
    "copy_start": {"ja": "[BUILD] アプリケーションファイルをコピー中...", "en": "[BUILD] Copying application files...", "ko": "[BUILD] 애플리케이션 파일 복사 중...", "zh_TW": "[BUILD] 正在複製應用程式檔案...", "zh_CN": "[BUILD] 正在复制应用程序文件..."},
    "copy_done": {"ja": "[BUILD] {n} 項目コピー完了", "en": "[BUILD] {n} items copied", "ko": "[BUILD] {n}개 항목 복사 완료", "zh_TW": "[BUILD] 已複製 {n} 個項目", "zh_CN": "[BUILD] 已复制 {n} 个项目"},
    "ts_skip_existing": {"ja": "[BUILD] ビルド済み dist/ を検出 -- TS ビルドをスキップ", "en": "[BUILD] Pre-built dist/ found -- skipping TS build", "ko": "[BUILD] 빌드된 dist/ 감지 -- TS 빌드 건너뜀", "zh_TW": "[BUILD] 偵測到已建置的 dist/ -- 跳過 TS 建置", "zh_CN": "[BUILD] 检测到已构建的 dist/ -- 跳过 TS 构建"},
    "ts_no_build_mjs": {"ja": "[WARN] build.mjs が見つかりません -- TS ビルドをスキップ", "en": "[WARN] build.mjs not found -- skipping TS build", "ko": "[WARN] build.mjs를 찾을 수 없음 -- TS 빌드 건너뜀", "zh_TW": "[WARN] 找不到 build.mjs -- 跳過 TS 建置", "zh_CN": "[WARN] 找不到 build.mjs -- 跳过 TS 构建"},
    "ts_no_node": {"ja": "[WARN] Node.js が見つかりません -- TS ビルドをスキップ", "en": "[WARN] Node.js not found -- skipping TS build", "ko": "[WARN] Node.js를 찾을 수 없음 -- TS 빌드 건너뜀", "zh_TW": "[WARN] 找不到 Node.js -- 跳過 TS 建置", "zh_CN": "[WARN] 找不到 Node.js -- 跳过 TS 构建"},
    "ts_pkg_install": {"ja": "[BUILD] {mgr} install 実行中...", "en": "[BUILD] Running {mgr} install...", "ko": "[BUILD] {mgr} install 실행 중...", "zh_TW": "[BUILD] 正在執行 {mgr} install...", "zh_CN": "[BUILD] 正在执行 {mgr} install..."},
    "ts_build_start": {"ja": "[BUILD] TypeScript ビルド実行中...", "en": "[BUILD] Running TypeScript build...", "ko": "[BUILD] TypeScript 빌드 실행 중...", "zh_TW": "[BUILD] 正在執行 TypeScript 建置...", "zh_CN": "[BUILD] 正在执行 TypeScript 构建..."},
    "ts_build_done": {"ja": "[BUILD] TypeScript ビルド完了", "en": "[BUILD] TypeScript build complete", "ko": "[BUILD] TypeScript 빌드 완료", "zh_TW": "[BUILD] TypeScript 建置完成", "zh_CN": "[BUILD] TypeScript 构建完成"},
    "arg_desc": {"ja": "YU AI Manager ポータブル版ビルド", "en": "YU AI Manager portable build", "ko": "YU AI Manager 포터블 버전 빌드", "zh_TW": "YU AI Manager 可攜版建置", "zh_CN": "YU AI Manager 便携版构建"},
    "arg_pyver": {"ja": "同梱する Python のバージョン (default: 3.13.15)", "en": "Python version to bundle (default: 3.13.15)", "ko": "번들할 Python 버전 (default: 3.13.15)", "zh_TW": "要打包的 Python 版本 (default: 3.13.15)", "zh_CN": "要打包的 Python 版本 (default: 3.13.15)"},
    "arg_outdir": {"ja": "ZIP 出力先ディレクトリ (default: ./release)", "en": "ZIP output directory (default: ./release)", "ko": "ZIP 출력 디렉터리 (default: ./release)", "zh_TW": "ZIP 輸出目錄 (default: ./release)", "zh_CN": "ZIP 输出目录 (default: ./release)"},
    "arg_skip_ts": {"ja": "TypeScript ビルドをスキップ (dist/ が既にある場合)", "en": "Skip TypeScript build (if dist/ already exists)", "ko": "TypeScript 빌드 건너뛰기 (dist/가 이미 있는 경우)", "zh_TW": "跳過 TypeScript 建置 (若 dist/ 已存在)", "zh_CN": "跳过 TypeScript 构建 (若 dist/ 已存在)"},
    "err_windows_only": {"ja": "[ERROR] ポータブル版ビルドは Windows 上でのみ実行できます", "en": "[ERROR] Portable build can only run on Windows", "ko": "[ERROR] 포터블 빌드는 Windows에서만 실행할 수 있습니다", "zh_TW": "[ERROR] 可攜版建置僅能在 Windows 上執行", "zh_CN": "[ERROR] 便携版构建只能在 Windows 上执行"},
    "build_start": {"ja": "[BUILD] YU AI Manager v{ver} ポータブル版ビルド開始", "en": "[BUILD] Starting YU AI Manager v{ver} portable build", "ko": "[BUILD] YU AI Manager v{ver} 포터블 빌드 시작", "zh_TW": "[BUILD] 開始建置 YU AI Manager v{ver} 可攜版", "zh_CN": "[BUILD] 开始构建 YU AI Manager v{ver} 便携版"},
    "build_python_label": {"ja": "  Python: {ver}", "en": "  Python: {ver}", "ko": "  Python: {ver}", "zh_TW": "  Python: {ver}", "zh_CN": "  Python: {ver}"},
    "build_output_label": {"ja": "  出力: {path}", "en": "  Output: {path}", "ko": "  출력: {path}", "zh_TW": "  輸出: {path}", "zh_CN": "  输出: {path}"},
    "err_no_dist_js": {"ja": "[ERROR] ui/default/static/dist/ にビルド済み JS がありません", "en": "[ERROR] No built JS found in ui/default/static/dist/", "ko": "[ERROR] ui/default/static/dist/에 빌드된 JS가 없습니다", "zh_TW": "[ERROR] ui/default/static/dist/ 中沒有已建置的 JS", "zh_CN": "[ERROR] ui/default/static/dist/ 中没有已构建的 JS"},
    "err_run_build_first": {"ja": "  先に pnpm run build を実行してください", "en": "  Please run pnpm run build first", "ko": "  먼저 pnpm run build를 실행하세요", "zh_TW": "  請先執行 pnpm run build", "zh_CN": "  请先执行 pnpm run build"},
    "zip_creating": {"ja": "[BUILD] ZIP 作成中: {path}", "en": "[BUILD] Creating ZIP: {path}", "ko": "[BUILD] ZIP 생성 중: {path}", "zh_TW": "[BUILD] 正在建立 ZIP: {path}", "zh_CN": "[BUILD] 正在创建 ZIP: {path}"},
    "build_done": {"ja": "[BUILD] 完了: {path} ({size} MB)", "en": "[BUILD] Done: {path} ({size} MB)", "ko": "[BUILD] 완료: {path} ({size} MB)", "zh_TW": "[BUILD] 完成: {path} ({size} MB)", "zh_CN": "[BUILD] 完成: {path} ({size} MB)"},
}


def msg(lang: str, key: str) -> str:
    return MESSAGES[key].get(lang, MESSAGES[key]["en"])
