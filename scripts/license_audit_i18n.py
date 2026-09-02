"""Localization helpers for license audit."""

import locale
import os


def _detect_lang():
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


_LANG = _detect_lang()

_MSG = {
    "title": {"en": "  YU AI Manager License Compliance Audit", "ja": "  YU AI Manager ライセンスコンプライアンス監査", "ko": "  YU AI Manager 라이선스 컴플라이언스 감사", "zh_TW": "  YU AI Manager 授權合規稽核", "zh_CN": "  YU AI Manager 许可合规审计"},
    "chk1_header": {"en": "=== Check 1: Python package licenses (pip-licenses) ===", "ja": "=== チェック 1: Python パッケージライセンス (pip-licenses) ===", "ko": "=== 검사 1: Python 패키지 라이선스 (pip-licenses) ===", "zh_TW": "=== 檢查 1: Python 套件授權 (pip-licenses) ===", "zh_CN": "=== 检查 1: Python 包许可 (pip-licenses) ==="},
    "skip_pip_licenses": {"en": "  [SKIP] pip-licenses not available: {err}", "ja": "  [SKIP] pip-licenses が利用できません: {err}", "ko": "  [SKIP] pip-licenses를 사용할 수 없습니다: {err}", "zh_TW": "  [SKIP] pip-licenses 不可用: {err}", "zh_CN": "  [SKIP] pip-licenses 不可用: {err}"},
    "chk1_label": {"en": "No GPL/LGPL/AGPL-only packages ({n} total)", "ja": "GPL/LGPL/AGPL 専用パッケージなし ({n} 件中)", "ko": "GPL/LGPL/AGPL 전용 패키지 없음 (전체 {n}개)", "zh_TW": "無 GPL/LGPL/AGPL 專用套件 (共 {n} 個)", "zh_CN": "无 GPL/LGPL/AGPL 专用包 (共 {n} 个)"},
    "chk2_header": {"en": "=== Check 2: Source code GPL/LGPL license headers ===", "ja": "=== チェック 2: ソースコードの GPL/LGPL ライセンスヘッダー ===", "ko": "=== 검사 2: 소스 코드 GPL/LGPL 라이선스 헤더 ===", "zh_TW": "=== 檢查 2: 原始碼 GPL/LGPL 授權標頭 ===", "zh_CN": "=== 检查 2: 源代码 GPL/LGPL 许可头 ==="},
    "chk2_label": {"en": "No GPL/LGPL license headers in source", "ja": "ソースコードに GPL/LGPL ライセンスヘッダーなし", "ko": "소스 코드에 GPL/LGPL 라이선스 헤더 없음", "zh_TW": "原始碼中無 GPL/LGPL 授權標頭", "zh_CN": "源代码中无 GPL/LGPL 许可头"},
    "chk2_found": {"en": "{n} found", "ja": "{n} 件検出", "ko": "{n}건 발견", "zh_TW": "發現 {n} 個", "zh_CN": "发现 {n} 个"},
    "chk3_header": {"en": "=== Check 3: LICENSE/COPYING files ===", "ja": "=== チェック 3: LICENSE/COPYING ファイル ===", "ko": "=== 검사 3: LICENSE/COPYING 파일 ===", "zh_TW": "=== 檢查 3: LICENSE/COPYING 檔案 ===", "zh_CN": "=== 检查 3: LICENSE/COPYING 文件 ==="},
    "chk3_label": {"en": "No GPL LICENSE/COPYING files ({n} checked)", "ja": "GPL の LICENSE/COPYING ファイルなし ({n} 件確認)", "ko": "GPL LICENSE/COPYING 파일 없음 ({n}개 확인)", "zh_TW": "無 GPL LICENSE/COPYING 檔案 (已檢查 {n} 個)", "zh_CN": "无 GPL LICENSE/COPYING 文件 (已检查 {n} 个)"},
    "chk4_header": {"en": "=== Check 4: requirements.txt known-bad packages ===", "ja": "=== チェック 4: requirements.txt の既知の問題パッケージ ===", "ko": "=== 검사 4: requirements.txt 알려진 문제 패키지 ===", "zh_TW": "=== 檢查 4: requirements.txt 已知問題套件 ===", "zh_CN": "=== 检查 4: requirements.txt 已知问题包 ==="},
    "skip_no_req": {"en": "  [SKIP] requirements.txt not found", "ja": "  [SKIP] requirements.txt が見つかりません", "ko": "  [SKIP] requirements.txt를 찾을 수 없습니다", "zh_TW": "  [SKIP] 找不到 requirements.txt", "zh_CN": "  [SKIP] 找不到 requirements.txt"},
    "chk4_label": {"en": "No known GPL/LGPL packages in requirements.txt", "ja": "requirements.txt に既知の GPL/LGPL パッケージなし", "ko": "requirements.txt에 알려진 GPL/LGPL 패키지 없음", "zh_TW": "requirements.txt 中無已知 GPL/LGPL 套件", "zh_CN": "requirements.txt 中无已知 GPL/LGPL 包"},
    "chk5_header": {"en": "=== Check 5: THIRD_PARTY_LICENSES.txt ===", "ja": "=== チェック 5: THIRD_PARTY_LICENSES.txt ===", "ko": "=== 검사 5: THIRD_PARTY_LICENSES.txt ===", "zh_TW": "=== 檢查 5: THIRD_PARTY_LICENSES.txt ===", "zh_CN": "=== 检查 5: THIRD_PARTY_LICENSES.txt ==="},
    "chk5_label": {"en": "THIRD_PARTY_LICENSES.txt exists", "ja": "THIRD_PARTY_LICENSES.txt が存在する", "ko": "THIRD_PARTY_LICENSES.txt 존재함", "zh_TW": "THIRD_PARTY_LICENSES.txt 存在", "zh_CN": "THIRD_PARTY_LICENSES.txt 存在"},
    "results": {"en": "  Results: {passed} passed, {failed} failed", "ja": "  結果: {passed} 成功, {failed} 失敗", "ko": "  결과: {passed} 통과, {failed} 실패", "zh_TW": "  結果: {passed} 通過, {failed} 失敗", "zh_CN": "  结果: {passed} 通过, {failed} 失败"},
}


def msg(key):
    return _MSG[key].get(_LANG, _MSG[key]["en"])
