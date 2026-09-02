"""MCP tools for Speech-to-Text."""

import json

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .validators import validate_batch_size, validate_file_id, validate_path


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def register_s2t_tools(mcp: FastMCP, client: YuManagerClient):
    """Register Speech-to-Text tools on the MCP server."""

    @mcp.tool()
    def s2t_status() -> str:
        """Get Speech-to-Text backend status and available backends."""
        return _json(client.get("/ext/speech-to-text/api/s2t/status"))

    @mcp.tool()
    def s2t_transcribe_video(file_id: int, language: str = "") -> str:
        """Transcribe audio from a video/audio file and save as annotation.

        Args:
            file_id: The file ID to transcribe
            language: Language code (e.g. 'ja', 'en'). Empty = use default.
        """
        err = validate_file_id(file_id)
        if err:
            return err
        body = {"file_id": file_id}
        if language.strip():
            body["language"] = language.strip()
        return _json(client.post(
            "/ext/speech-to-text/api/s2t/transcribe-video", body,
        ))

    @mcp.tool()
    def s2t_batch_transcribe(
        file_ids: list | None = None,
        directory: str = "",
        list_file: str = "",
        recursive: bool = True,
        language: str = "",
        expected_count: int = 0,
    ) -> str:
        """Start batch transcription of multiple video/audio files in background.

        3 つの入力方式から 1 つを選択 (排他的):

        1. file_ids: ファイル ID リスト (最大 500)
        2. directory: ディレクトリパス (配下の動画/音声を自動検出)
        3. list_file: テキスト/CSV ファイルパス (1 行 1 ファイルパス)

        Args:
            file_ids: List of file IDs to transcribe. Max 500.
            directory: Directory path. Media files inside are auto-detected.
            list_file: Path to .txt or .csv file listing target file paths.
            recursive: When using directory mode, search subdirectories. Default True.
            language: Language code (e.g. 'ja', 'en', 'zh'). Empty = use default setting.
            expected_count: Number of file_ids you intended (truncation guard, file_ids mode only)
        """
        # Exclusive input mode check
        has_ids = file_ids is not None and len(file_ids) > 0
        has_dir = bool(directory.strip())
        has_list = bool(list_file.strip())
        mode_count = sum([has_ids, has_dir, has_list])

        if mode_count == 0:
            return _json({"ok": False, "error": "file_ids, directory, list_file のいずれかを指定してください"})
        if mode_count > 1:
            return _json({"ok": False, "error": "file_ids, directory, list_file は排他的です"})

        body: dict = {}

        if has_ids:
            err = validate_batch_size(file_ids, expected_count)
            if err:
                return err
            body["file_ids"] = file_ids
        elif has_dir:
            err = validate_path(directory)
            if err:
                return err
            body["directory"] = directory.strip()
            body["recursive"] = recursive
        else:
            err = validate_path(list_file)
            if err:
                return err
            body["list_file"] = list_file.strip()

        if language.strip():
            body["language"] = language.strip()

        return _json(client.post(
            "/ext/speech-to-text/api/s2t/batch-transcribe", body,
        ))

    @mcp.tool()
    def s2t_get_transcript(file_id: int) -> str:
        """Get saved transcript for a file.

        Args:
            file_id: The file ID to get transcript for
        """
        err = validate_file_id(file_id)
        if err:
            return err
        return _json(client.get(
            f"/ext/speech-to-text/api/s2t/transcript/{file_id}",
        ))

    @mcp.tool()
    def s2t_stream_start(
        source_url: str,
        language: str = "ja",
        mode: str = "chunk",
        model_size: str = "",
    ) -> str:
        """Start real-time stream transcription from a URL source.

        Args:
            source_url: URL of the audio/video stream (http, https, rtsp, rtmp)
            language: Language code for transcription (e.g. 'ja', 'en'). Default 'ja'.
            mode: Transcription mode. 'chunk' = fixed-interval decoding (Phase A),
                  'live' = VAD-based streaming with interim results (Phase B). Default 'chunk'.
            model_size: Whisper model size override (e.g. 'tiny', 'base', 'small', 'medium',
                        'large'). Empty = use server default.
        """
        url = source_url.strip()
        if not url:
            return _json({"ok": False, "error": "source_url is required"})
        if mode not in ("chunk", "live"):
            return _json({"ok": False, "error": "mode must be 'chunk' or 'live'"})
        body: dict = {"source_url": url, "language": language, "mode": mode}
        if model_size.strip():
            body["model_size"] = model_size.strip()
        return _json(client.post(
            "/ext/speech-to-text/api/s2t/stream/start",
            body,
        ))

    @mcp.tool()
    def s2t_stream_stop() -> str:
        """Stop the currently running stream transcription."""
        return _json(client.post(
            "/ext/speech-to-text/api/s2t/stream/stop", {},
        ))

    @mcp.tool()
    def s2t_stream_status() -> str:
        """Get current stream transcription status (running, stopped, etc.)."""
        return _json(client.get(
            "/ext/speech-to-text/api/s2t/stream/status",
        ))

    @mcp.tool()
    def s2t_stream_transcript() -> str:
        """Get accumulated transcript from the running or completed stream."""
        return _json(client.get(
            "/ext/speech-to-text/api/s2t/stream/transcript",
        ))

    @mcp.tool()
    def s2t_export_transcript_txt() -> str:
        """Export stream transcript as plain text.

        Returns the transcript text content as a string.
        """
        return client.get_text(
            "/ext/speech-to-text/api/s2t/stream/export/txt",
        )

    @mcp.tool()
    def s2t_export_transcript_srt() -> str:
        """Export stream transcript as SRT subtitle format.

        Returns the SRT content as a string.
        """
        return client.get_text(
            "/ext/speech-to-text/api/s2t/stream/export/srt",
        )

    @mcp.tool()
    def s2t_stream_llm_process(mode: str, target_lang: str = "") -> str:
        """Post-process the stream transcript with an LLM.

        Args:
            mode: Processing mode. One of:
                  'refine'    — clean up recognition errors and add punctuation,
                  'translate' — translate to target_lang,
                  'summarize' — produce a concise summary.
            target_lang: Target language for translation (e.g. 'en', 'ja').
                         Required when mode is 'translate', ignored otherwise.
        """
        if mode not in ("refine", "translate", "summarize"):
            return _json({"ok": False, "error": "mode must be 'refine', 'translate', or 'summarize'"})
        body: dict = {"mode": mode}
        if target_lang.strip():
            body["target_lang"] = target_lang.strip()
        return _json(client.post(
            "/ext/speech-to-text/api/s2t/stream/llm-process",
            body,
        ))
