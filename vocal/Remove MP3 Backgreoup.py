import os
import re
import sys
import threading
import subprocess

import customtkinter as ctk
from tkinterdnd2 import DND_FILES, TkinterDnD

# ------------------- 설정 -------------------
MODEL = "htdemucs_ft"   # 보컬 품질이 가장 좋은 fine-tuned 모델
# 속도가 더 중요하면 "htdemucs" 로 바꾸세요 (약 4배 빠름, 품질 손실 미미)

OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "Vocals_Output")
SUPPORTED = (".mp3", ".wav", ".flac", ".m4a", ".ogg")

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def detect_device():
    """torch가 GPU(CUDA)를 쓸 수 있으면 'cuda', 아니면 'cpu' 반환."""
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda", torch.cuda.get_device_name(0)
    except Exception:
        pass
    return "cpu", None


class App(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self):
        super().__init__()
        self.TkdndVersion = TkinterDnD._require(self)

        # 실행 시점에 GPU 사용 가능 여부 판별
        self.device, self.gpu_name = detect_device()

        self.title("보컬 추출기  ·  " + MODEL)
        self.geometry("520x470")
        self.minsize(460, 430)
        self.is_processing = False
        self.last_output = None

        # ---- 제목 ----
        ctk.CTkLabel(self, text="🎤  보컬만 추출하기",
                     font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(24, 4))
        ctk.CTkLabel(self, text="목소리만 남기고 배경음악을 제거합니다",
                     font=ctk.CTkFont(size=13), text_color="gray70").pack(pady=(0, 6))

        # ---- 장치 표시 ----
        if self.device == "cuda":
            dev_text = f"⚡ GPU 가속 사용 중  ·  {self.gpu_name}"
            dev_color = "#4ade80"
        else:
            dev_text = "🐢 CPU 모드 (느림) — GPU 버전 torch 설치를 권장합니다"
            dev_color = "#fbbf24"
        ctk.CTkLabel(self, text=dev_text,
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=dev_color).pack(pady=(0, 14))

        # ---- 드롭 영역 ----
        self.drop_frame = ctk.CTkFrame(
            self, height=150, corner_radius=16,
            border_width=2, border_color="gray40", fg_color="gray17")
        self.drop_frame.pack(fill="x", padx=30, pady=6)
        self.drop_frame.pack_propagate(False)
        self.drop_label = ctk.CTkLabel(
            self.drop_frame,
            text="⬇  여기에 오디오 파일을 드롭하세요\n\n(mp3, wav, flac, m4a, ogg)",
            font=ctk.CTkFont(size=15), justify="center")
        self.drop_label.pack(expand=True)

        # ---- 진행률 ----
        self.progress = ctk.CTkProgressBar(self, height=14, corner_radius=8)
        self.progress.set(0)
        self.progress.pack(fill="x", padx=30, pady=(18, 4))

        self.status_label = ctk.CTkLabel(
            self, text="대기 중 — 파일을 드롭하면 시작합니다.",
            font=ctk.CTkFont(size=13), wraplength=440, justify="center")
        self.status_label.pack(pady=(2, 8))

        # ---- 버튼 ----
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=(4, 14))
        self.open_btn = ctk.CTkButton(
            btn_frame, text="📂 결과 폴더 열기",
            command=self.open_output, state="disabled", width=160)
        self.open_btn.grid(row=0, column=0, padx=6)
        self.reset_btn = ctk.CTkButton(
            btn_frame, text="🔄 다시 하기", command=self.reset,
            fg_color="gray30", hover_color="gray25", width=120)
        self.reset_btn.grid(row=0, column=1, padx=6)

        # ---- 드래그앤드롭 등록 ----
        self.drop_target_register(DND_FILES)
        self.dnd_bind("<<Drop>>", self.on_drop)

    # ---------- 드롭 처리 ----------
    def on_drop(self, event):
        if self.is_processing:
            self.set_status("이미 처리 중이에요. 잠시만 기다려주세요.")
            return
        files = self.tk.splitlist(event.data)
        if not files:
            self.set_status("파일을 인식하지 못했어요. 다시 시도해주세요.")
            return

        first = files[0]
        ext = os.path.splitext(first)[1].lower()
        audio = [f for f in files if f.lower().endswith(SUPPORTED)]

        if not audio:
            self.set_status(
                f"지원하지 않는 형식이에요.\n"
                f"드롭한 파일: {os.path.basename(first)}\n"
                f"인식된 확장자: '{ext or '(없음)'}'\n"
                f"지원 형식: mp3, wav, flac, m4a, ogg"
            )
            return

        threading.Thread(target=self.separate, args=(audio[0],), daemon=True).start()

    # ---------- 분리 실행 ----------
    def separate(self, file_path, segment=None):
        self.is_processing = True
        self.last_output = None
        self.after(0, lambda: self.open_btn.configure(state="disabled"))
        self.set_progress(0.02)
        name = os.path.basename(file_path)

        dev_msg = "GPU" if self.device == "cuda" else "CPU"
        self.set_status(
            f"모델 준비 중... ({dev_msg} 모드)  ({name})\n"
            f"첫 실행 시 모델 다운로드로 시간이 걸릴 수 있어요."
        )

        try:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            cmd = [
                sys.executable, "-m", "demucs",
                "-n", MODEL,
                "-d", self.device,          # cuda(GPU) 또는 cpu 자동 선택
                "--two-stems", "vocals",
                "--mp3",
                "-o", OUTPUT_DIR,
            ]
            # VRAM 부족(OOM) 재시도 시 세그먼트 분할 적용
            if segment is not None:
                cmd += ["--segment", str(segment)]
            cmd.append(file_path)

            creationflags = 0
            startupinfo = None
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                creationflags = subprocess.CREATE_NO_WINDOW

            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, startupinfo=startupinfo,
                creationflags=creationflags)

            pct_re = re.compile(r"(\d{1,3})%")
            last_lines = []
            for line in proc.stdout:
                line = line.strip()
                if line:
                    last_lines.append(line)
                    last_lines = last_lines[-8:]
                m = pct_re.search(line)
                if m:
                    p = int(m.group(1)) / 100
                    self.set_progress(max(0.02, p))
                    self.set_status(f"분리 중... ({dev_msg})  {int(p*100)}%   ({name})")

            proc.wait()

            if proc.returncode != 0:
                full_log = "\n".join(last_lines)

                # GPU 메모리 부족(OOM) 감지 → 세그먼트 줄여서 자동 재시도
                oom = ("out of memory" in full_log.lower()
                       or "cuda error" in full_log.lower())
                if oom and self.device == "cuda" and segment is None:
                    self.set_status("⚠ GPU 메모리 부족 — 조각 분할 모드로 다시 시도합니다...")
                    self.is_processing = False
                    self.separate(file_path, segment=7)   # 재시도
                    return

                msg = full_log or "알 수 없는 오류"
                self.set_status("❌ demucs 실행 실패:\n" + msg[-400:])
                self.set_progress(0)
                return

            song = os.path.splitext(name)[0]
            vocal_file = os.path.join(OUTPUT_DIR, MODEL, song, "vocals.mp3")
            self.last_output = os.path.dirname(vocal_file)
            self.set_progress(1.0)
            self.set_status(f"✅ 완료!  보컬 파일이 저장되었습니다.\n{vocal_file}")
            self.after(0, lambda: self.open_btn.configure(state="normal"))

        except FileNotFoundError:
            self.set_status("❌ demucs를 찾을 수 없어요.\n'pip install demucs' 설치를 확인하세요.")
            self.set_progress(0)
        except Exception as e:
            self.set_status(f"❌ 오류: {e}")
            self.set_progress(0)
        finally:
            self.is_processing = False

    # ---------- 유틸 ----------
    def set_status(self, text):
        self.after(0, lambda: self.status_label.configure(text=text))

    def set_progress(self, value):
        self.after(0, lambda: self.progress.set(value))

    def open_output(self):
        target = self.last_output or OUTPUT_DIR
        if os.path.isdir(target):
            os.startfile(target)

    def reset(self):
        if self.is_processing:
            return
        self.progress.set(0)
        self.last_output = None
        self.open_btn.configure(state="disabled")
        self.set_status("대기 중 — 파일을 드롭하면 시작합니다.")


if __name__ == "__main__":
    App().mainloop()
