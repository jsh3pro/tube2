# transcript.py
import os
import re
import requests
from http.cookiejar import MozillaCookieJar
from urllib.parse import urlparse, parse_qs
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)


# 쿠키 파일 경로 (app.py와 같은 폴더의 cookies.txt)
COOKIE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "cookies.txt"
)


def extract_video_id(url: str):
    """다양한 형태의 유튜브 URL에서 영상 ID 추출."""
    if not url:
        return None
    url = url.strip()

    # youtu.be 단축 URL
    if "youtu.be/" in url:
        match = re.search(r"youtu\.be/([A-Za-z0-9_-]{11})", url)
        if match:
            return match.group(1)

    # youtube.com/shorts/
    if "/shorts/" in url:
        match = re.search(r"/shorts/([A-Za-z0-9_-]{11})", url)
        if match:
            return match.group(1)

    # youtube.com/live/
    if "/live/" in url:
        match = re.search(r"/live/([A-Za-z0-9_-]{11})", url)
        if match:
            return match.group(1)

    # 일반 watch URL (m.youtube.com 포함)
    parsed = urlparse(url)
    if "youtube.com" in parsed.netloc:
        qs = parse_qs(parsed.query)
        if "v" in qs and len(qs["v"][0]) == 11:
            return qs["v"][0]

    # ID만 들어온 경우
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url):
        return url

    return None


def get_video_title(video_id: str):
    """유튜브 oEmbed API로 영상 제목 가져오기."""
    try:
        resp = requests.get(
            "https://www.youtube.com/oembed",
            params={
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "format": "json",
            },
            timeout=5,
        )
        if resp.status_code == 200:
            return resp.json().get("title")
    except Exception:
        pass
    return None


def sanitize_filename(name: str, max_length: int = 50) -> str:
    """파일명에서 금지 문자 제거 및 길이 제한."""
    if not name:
        return ""
    forbidden = r'[\\/:*?"<>|\n\r\t]'
    cleaned = re.sub(forbidden, "_", name)
    cleaned = re.sub(r"_+", "_", cleaned)
    cleaned = cleaned.strip(" _")
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip(" _")
    return cleaned


def build_filename(title, video_id: str) -> str:
    """다운로드 파일명 생성."""
    safe_title = sanitize_filename(title) if title else ""
    if safe_title:
        return f"{safe_title}_{video_id}.txt"
    return f"transcript_{video_id}.txt"


def format_timestamp(seconds: float) -> str:
    """초 단위 → [HH:MM:SS] 형식."""
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"[{h:02d}:{m:02d}:{s:02d}]"


def remove_overlap(prev_text: str, curr_text: str) -> str:
    """이전 줄 끝과 현재 줄 시작이 겹치는 부분 제거."""
    if not prev_text or not curr_text:
        return curr_text

    prev_words = prev_text.split()
    curr_words = curr_text.split()
    max_check = min(len(prev_words), len(curr_words))

    for n in range(max_check, 0, -1):
        if prev_words[-n:] == curr_words[:n]:
            return " ".join(curr_words[n:])
    return curr_text


def _build_session_with_cookies(verbose: bool = True):
    """cookies.txt가 있으면 쿠키를 로드한 requests.Session을 반환.
    없으면 일반 Session 반환.

    Args:
        verbose: True면 쿠키 로드 상태를 콘솔에 출력 (기본값).
                 채널 모드에서는 False로 호출하여 로그 폭주 방지.
    """
    session = requests.Session()
    # 일반 브라우저처럼 보이게 User-Agent도 같이 설정
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    })

    if os.path.exists(COOKIE_FILE):
        try:
            jar = MozillaCookieJar(COOKIE_FILE)
            jar.load(ignore_discard=True, ignore_expires=True)
            session.cookies = jar
            if verbose:
                print(f"[transcript] 쿠키 로드 성공: {COOKIE_FILE}")
        except Exception as e:
            # 쿠키 로드 실패해도 일단 진행 (없는 것과 동일)
            if verbose:
                print(f"[transcript] 쿠키 로드 실패: {e}")
    else:
        if verbose:
            print(f"[transcript] 쿠키 파일 없음 (쿠키 없이 진행): {COOKIE_FILE}")

    return session


def fetch_transcript(video_id: str, session=None) -> dict:
    """자막을 가져와 가공된 결과 반환.

    우선순위: 한국어 수동 → 한국어 자동.

    Args:
        video_id: 유튜브 영상 ID.
        session: 외부에서 주입할 requests.Session (선택).
                 None이면 내부에서 새로 생성 (기존 단건 동작).
                 채널 모드에서는 세션 1개를 재사용하여 호출.
    """
    if session is None:
        session = _build_session_with_cookies()
    ytt_api = YouTubeTranscriptApi(http_client=session)

    # 자막 목록 조회
    try:
        transcript_list = ytt_api.list(video_id)
    except TranscriptsDisabled:
        raise ValueError("이 영상은 자막이 비활성화되어 있습니다.")
    except VideoUnavailable:
        raise ValueError("영상을 찾을 수 없거나 접근할 수 없습니다.")
    except Exception as e:
        raise ValueError(f"자막 목록을 가져오는 중 오류가 발생했습니다: {e}")

    # 한국어 수동 자막 우선 시도
    chosen = None
    kind = None
    try:
        chosen = transcript_list.find_manually_created_transcript(["ko"])
        kind = "manual"
    except NoTranscriptFound:
        pass

    # 없으면 한국어 자동 자막
    if chosen is None:
        try:
            chosen = transcript_list.find_generated_transcript(["ko"])
            kind = "auto"
        except NoTranscriptFound:
            pass

    if chosen is None:
        raise ValueError("이 영상에는 한국어 자막(수동/자동)이 없습니다.")

    # 실제 자막 데이터 가져오기
    try:
        fetched = chosen.fetch()
    except Exception as e:
        raise ValueError(f"자막을 다운로드하는 중 오류가 발생했습니다: {e}")

    # 가공: 줄마다 타임스탬프 + 앞 줄과 겹치는 부분 제거
    lines = []
    prev_text = ""
    for snippet in fetched:
        # FetchedTranscriptSnippet 객체: .text, .start, .duration
        text = snippet.text.replace("\n", " ").strip()
        if not text:
            continue
        cleaned = remove_overlap(prev_text, text)
        if not cleaned:
            continue
        ts = format_timestamp(snippet.start)
        lines.append((ts, cleaned))
        prev_text = text  # 비교는 원본 기준

    full_text = "\n".join(f"{ts} {txt}" for ts, txt in lines)

    return {
        "kind": kind,
        "language": "ko",
        "lines": lines,
        "full_text": full_text,
    }


def make_preview(full_text: str, max_chars: int = 100) -> str:
    """미리보기 텍스트 생성: 약 100자, 어절 경계에서 자르고 ... 붙임."""
    body = re.sub(r"\[\d{2}:\d{2}:\d{2}\]\s*", "", full_text)
    body = re.sub(r"\s+", " ", body).strip()

    if len(body) <= max_chars:
        return body

    cut = body[:max_chars]
    last_space = cut.rfind(" ")
    if last_space > max_chars * 0.6:
        cut = cut[:last_space]
    return cut.rstrip() + "..."
