# app.py
import os
from flask import Flask, request, jsonify, send_from_directory

from transcript import (
    extract_video_id,
    get_video_title,
    build_filename,
    fetch_transcript,
    make_preview,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)


@app.route("/", methods=["GET"])
def index():
    """HTML 페이지 서빙."""
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/api/transcript", methods=["POST"])
def api_transcript():
    """유튜브 URL을 받아 자막을 가공하여 반환."""
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()

    if not url:
        return jsonify({"ok": False, "error": "URL이 입력되지 않았습니다."}), 400

    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({"ok": False, "error": "유효한 유튜브 URL이 아닙니다."}), 400

    try:
        result = fetch_transcript(video_id)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    except Exception as e:
        return jsonify({"ok": False, "error": f"예기치 못한 오류: {e}"}), 500

    title = get_video_title(video_id)
    filename = build_filename(title, video_id)
    preview = make_preview(result["full_text"], max_chars=100)

    return jsonify({
        "ok": True,
        "video_id": video_id,
        "title": title or "",
        "kind": result["kind"],            # "manual" or "auto"
        "language": result["language"],
        "filename": filename,
        "preview": preview,
        "full_text": result["full_text"],
        "line_count": len(result["lines"]),
    })


@app.route("/api/health", methods=["GET"])
def health():
    """서버 상태 확인용."""
    return jsonify({"ok": True, "message": "server is running"})


if __name__ == "__main__":
    # 127.0.0.1로만 바인딩 = 폰 내부에서만 접근 가능 (보안상 안전)
    app.run(host="127.0.0.1", port=5000, debug=False)
