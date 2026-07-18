# app.py
import os
import json
import threading
from flask import (
    Flask, request, jsonify, send_from_directory,
    Response, send_file, stream_with_context,
)

from transcript import (
    extract_video_id,
    get_video_title,
    build_filename,
    fetch_transcript,
    make_preview,
)
from channel_transcript import (
    parse_channel_handle,
    create_job,
    get_job,
    cleanup_job,
    run_channel_job,
    load_saved_channels,
    clear_cache,
    load_cache,
    DOWNLOAD_DIR,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)


# ============================================================
# 기존 단건 라우트 (변경 없음)
# ============================================================
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
        "kind": result["kind"],
        "language": result["language"],
        "filename": filename,
        "preview": preview,
        "full_text": result["full_text"],
        "line_count": len(result["lines"]),
    })


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "message": "server is running"})


# ============================================================
# 채널 모드 라우트 (신규)
# ============================================================
@app.route("/channel", methods=["GET"])
def channel_page():
    """채널 일괄 다운로드 페이지 서빙."""
    return send_from_directory(BASE_DIR, "channel.html")


@app.route("/api/channel/start", methods=["POST"])
def api_channel_start():
    """채널 일괄 다운로드 작업 시작.

    Body:
        {
            "channels": "여러줄 텍스트 또는 @핸들 배열",
            "max_count": 50,
            "date_start": "2025-01-01" or "",
            "date_end": "" or "2025-12-31",
            "min_minutes": 1 or null,
            "max_minutes": 60 or null,
            "exclude_shorts": true,
            "use_cache": true
        }
    """
    data = request.get_json(silent=True) or {}

    # 채널 입력 파싱
    raw = data.get("channels")
    if isinstance(raw, list):
        lines = raw
    else:
        lines = str(raw or "").splitlines()

    handles = []
    seen = set()
    for line in lines:
        h = parse_channel_handle(line)
        if h and h not in seen:
            handles.append(h)
            seen.add(h)

    if not handles:
        return jsonify({
            "ok": False,
            "error": "유효한 채널이 없습니다. '@채널ID' 형식으로 입력해주세요.",
        }), 400

    # max_count
    try:
        max_count = int(data.get("max_count") or 50)
    except (TypeError, ValueError):
        max_count = 50
    max_count = max(1, min(max_count, 500))  # 안전 상한

    # 길이 (분)
    def _to_float_or_none(v):
        if v is None or v == "":
            return None
        try:
            f = float(v)
            return f if f > 0 else None
        except (TypeError, ValueError):
            return None

    min_minutes = _to_float_or_none(data.get("min_minutes"))
    max_minutes = _to_float_or_none(data.get("max_minutes"))

    params = {
        "handles": handles,
        "max_count": max_count,
        "date_start": (data.get("date_start") or "").strip() or None,
        "date_end": (data.get("date_end") or "").strip() or None,
        "min_minutes": min_minutes,
        "max_minutes": max_minutes,
        "exclude_shorts": bool(data.get("exclude_shorts", True)),
        "use_cache": bool(data.get("use_cache", True)),
    }

    # 작업 생성 + 백그라운드 스레드 실행
    job = create_job()
    t = threading.Thread(
        target=run_channel_job,
        args=(job, params),
        daemon=True,
    )
    t.start()

    return jsonify({
        "ok": True,
        "job_id": job.job_id,
        "handles": handles,
    })


@app.route("/api/channel/stream/<job_id>", methods=["GET"])
def api_channel_stream(job_id: str):
    """SSE 스트림: 작업 진행 상황 실시간 전송."""
    job = get_job(job_id)
    if not job:
        return jsonify({"ok": False, "error": "작업을 찾을 수 없습니다."}), 404

    @stream_with_context
    def generate():
        # 시작 알림
        yield f"data: {json.dumps({'type': 'connected'}, ensure_ascii=False)}\n\n"

        sent = 0
        # 작업이 끝나고 모든 이벤트를 다 보낼 때까지 반복
        while True:
            with job.cond:
                # 새 이벤트가 올 때까지 대기 (최대 15초)
                while sent >= len(job.events) and not job.finished:
                    job.cond.wait(timeout=15)
                # 새 이벤트들 복사
                new_events = job.events[sent:]
                sent = len(job.events)
                finished = job.finished
                result_filename = job.result_filename

            for ev in new_events:
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

            if finished and sent >= len(job.events):
                # 종료 이벤트
                done_payload = {
                    "type": "done",
                    "result_filename": result_filename,
                    "download_url": (
                        f"/api/channel/download/{job_id}"
                        if result_filename else None
                    ),
                }
                yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
                break
            elif not new_events:
                # heartbeat (연결 유지)
                yield ": keepalive\n\n"

    headers = {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }
    return Response(generate(), headers=headers)


@app.route("/api/channel/download/<job_id>", methods=["GET"])
def api_channel_download(job_id: str):
    """완료된 작업의 ZIP 파일 다운로드."""
    job = get_job(job_id)
    if not job:
        return jsonify({"ok": False, "error": "작업을 찾을 수 없습니다."}), 404
    if not job.finished:
        return jsonify({"ok": False, "error": "작업이 아직 진행 중입니다."}), 409
    if not job.result_path or not os.path.exists(job.result_path):
        return jsonify({"ok": False, "error": "결과 파일이 없습니다."}), 404

    # 파일 전송 후에는 정리하지 않음 (사용자가 재다운로드할 수 있게)
    return send_file(
        job.result_path,
        as_attachment=True,
        download_name=job.result_filename,
        mimetype="application/zip",
    )


@app.route("/api/channel/cleanup/<job_id>", methods=["POST"])
def api_channel_cleanup(job_id: str):
    """작업 상태를 메모리에서 제거 (ZIP 파일은 디스크에 남음)."""
    cleanup_job(job_id)
    return jsonify({"ok": True})


@app.route("/api/channel/saved", methods=["GET"])
def api_channel_saved():
    """저장된 채널 목록 반환."""
    return jsonify({
        "ok": True,
        "channels": load_saved_channels(),
    })


@app.route("/api/channel/cache", methods=["GET"])
def api_channel_cache_status():
    """현재 캐시 상태 (받은 영상 수)."""
    cache = load_cache()
    return jsonify({"ok": True, "count": len(cache)})


@app.route("/api/channel/cache/clear", methods=["POST"])
def api_channel_cache_clear():
    """다운로드 캐시 초기화."""
    try:
        clear_cache()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
