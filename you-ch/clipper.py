# clipper.py
import os
import re
import shlex
from urllib.parse import urlparse, parse_qs
import yt_dlp


# 저장 경로 (갤럭시 다운로드 폴더 내 youtube_clips)
DOWNLOAD_DIR = os.path.expanduser("~/storage/shared/Download/youtube_clips")


def extract_video_id(url: str):
    """다양한 유튜브 URL에서 11자리 영상 ID 추출."""
    if not url:
        return None
    url = url.strip()

    if "youtu.be/" in url:
        m = re.search(r"youtu\.be/([A-Za-z0-9_-]{11})", url)
        if m:
            return m.group(1)

    if "/shorts/" in url:
        m = re.search(r"/shorts/([A-Za-z0-9_-]{11})", url)
        if m:
            return m.group(1)

    if "/live/" in url:
        m = re.search(r"/live/([A-Za-z0-9_-]{11})", url)
        if m:
            return m.group(1)

    parsed = urlparse(url)
    if "youtube.com" in parsed.netloc:
        qs = parse_qs(parsed.query)
        if "v" in qs and len(qs["v"][0]) == 11:
            return qs["v"][0]

    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url):
        return url

    return None


def parse_time_to_seconds(s: str):
    """'HH:MM:SS' / 'MM:SS' / 'SS' / '1:30' 등을 초 단위 정수로 변환.
    실패 시 None."""
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None

    # 숫자만 (초)
    if re.fullmatch(r"\d+", s):
        return int(s)

    # 소수점 초 (예: 90.5)
    if re.fullmatch(r"\d+\.\d+", s):
        return int(float(s))

    # HH:MM:SS 또는 MM:SS
    parts = s.split(":")
    if not all(re.fullmatch(r"\d+(\.\d+)?", p) for p in parts):
        return None

    try:
        nums = [float(p) for p in parts]
    except ValueError:
        return None

    if len(nums) == 2:
        m, sec = nums
        return int(m * 60 + sec)
    if len(nums) == 3:
        h, m, sec = nums
        return int(h * 3600 + m * 60 + sec)

    return None


def format_seconds_for_filename(total_seconds: int) -> str:
    """초 → '01h02m03s' 형태 (파일명용)."""
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    if h > 0:
        return f"{h:02d}h{m:02d}m{s:02d}s"
    return f"{m:02d}m{s:02d}s"


def sanitize_filename(name: str, max_length: int = 40) -> str:
    """파일명에서 금지 문자 제거 및 길이 제한."""
    if not name:
        return ""
    cleaned = re.sub(r'[\\/:*?"<>|\n\r\t]', "_", name)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned)
    cleaned = cleaned.strip(" _")
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip(" _")
    return cleaned


def build_filename(title, video_id: str, start_sec: int, end_sec: int) -> str:
    """파일명 생성: {제목}_{시작}-{종료}_{ID}.mp4"""
    safe_title = sanitize_filename(title) if title else ""
    start_s = format_seconds_for_filename(start_sec)
    end_s = format_seconds_for_filename(end_sec)
    if safe_title:
        return f"{safe_title}_{start_s}-{end_s}_{video_id}.mp4"
    return f"clip_{start_s}-{end_s}_{video_id}.mp4"


def get_video_info(url: str) -> dict:
    """yt-dlp로 영상 메타데이터만 조회 (다운로드 안 함)."""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return info


def download_clip(url: str, start_sec: int, end_sec: int,
                  progress_hook=None) -> dict:
    """유튜브 영상의 [start_sec, end_sec] 구간을 다운로드하여 저장.
    
    Returns:
        {
            "filepath": 저장된 절대 경로,
            "filename": 파일명,
            "title": 영상 제목,
            "video_id": 영상 ID,
            "format_desc": "1080p / 30fps / mp4" 같은 설명,
            "filesize": 파일 크기 (바이트),
        }
    """
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    video_id = extract_video_id(url)
    if not video_id:
        raise ValueError("유효한 유튜브 URL이 아닙니다.")

    # 먼저 메타데이터로 제목 확보 (파일명 생성용)
    try:
        info = get_video_info(url)
        title = info.get("title") or video_id
    except Exception as e:
        raise ValueError(f"영상 정보를 가져올 수 없습니다: {e}")

    filename = build_filename(title, video_id, start_sec, end_sec)
    filepath = os.path.join(DOWNLOAD_DIR, filename)

    # yt-dlp 옵션
    # format selector: 1080p mp4 h264 + m4a aac 우선 → 안 되면 차선 → 최후엔 best
    format_str = (
        "bestvideo[height<=1080][ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]"
        "/bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]"
        "/bestvideo[height<=1080]+bestaudio"
        "/best[height<=1080]"
        "/best"
    )

    ydl_opts = {
        "format": format_str,
        "outtmpl": filepath,
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
        # 핵심: 구간만 다운로드 (스트림 카피, 빠름)
        "download_ranges": yt_dlp.utils.download_range_func(
            None, [(start_sec, end_sec)]
        ),
        # 키프레임 강제 X (재인코딩 안 함 = 폰에 부담 없음)
        "force_keyframes_at_cuts": False,
    }

    if progress_hook is not None:
        ydl_opts["progress_hooks"] = [progress_hook]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        raise ValueError(f"다운로드 중 오류가 발생했습니다: {e}")

    # 실제 저장된 파일 확인 (yt-dlp가 확장자를 바꿀 수 있음)
    actual_path = filepath
    if not os.path.exists(actual_path):
        # 확장자가 다를 수 있어서 패턴 매칭
        base = os.path.splitext(filepath)[0]
        for ext in (".mp4", ".mkv", ".webm"):
            candidate = base + ext
            if os.path.exists(candidate):
                actual_path = candidate
                break
        else:
            raise ValueError("다운로드는 끝났지만 결과 파일을 찾을 수 없습니다.")

    # 받은 포맷 정보 추출
    height = info.get("height")
    fps = info.get("fps")
    ext = os.path.splitext(actual_path)[1].lstrip(".")
    parts = []
    if height:
        parts.append(f"{height}p")
    if fps:
        parts.append(f"{int(fps)}fps")
    if ext:
        parts.append(ext.upper())
    format_desc = " / ".join(parts) if parts else "알 수 없음"

    filesize = os.path.getsize(actual_path)

    return {
        "filepath": actual_path,
        "filename": os.path.basename(actual_path),
        "title": title,
        "video_id": video_id,
        "format_desc": format_desc,
        "filesize": filesize,
    }


def humanize_filesize(n: int) -> str:
    """바이트 → '12.3 MB' 같은 사람용 표기."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
