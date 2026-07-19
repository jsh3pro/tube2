import os
import threading
import subprocess
from tkinter import filedialog

import customtkinter as ctk
from tkinterdnd2 import DND_FILES, TkinterDnD

# ------------------- 설정 -------------------
DEFAULT_OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "Audio_Output")
SUPPORTED_VIDEO = (".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv")

# 형식별 ffmpeg 옵션 (확장자 -> 추가 인자)
FORMAT_OPTIONS = {
    "mp3":  ["-vn", "-q:a", "0"],
    "wav":  ["-vn"],
    "flac": ["-vn"],
    "m4a":  ["-vn", "-c:a", "aac", "-b:a", "256k"],
    "ogg":  ["-vn", "-c:a", "libvorbis", "-q:a", "5"],
}

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self):
        super().__init__()
        self.TkdndVersion = TkinterDnD._require(self)

        self.title("MP4 오디오 추출기")
        self.geometry("560x540")
        self.minsize(500, 500)
        self.is_processing = False
        self.last_output = None
        self.output_dir = DEFAULT_OUTPUT_DIR   # 현재 저장 폴더

        # ---- 제목 ----
        ctk.CTkLabel(self, text="🎬  영상에서 오디오 추출",
                     font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(24, 4))
        ctk.CTkLabel(self, text="영상 파일에서 음악/음성을 뽑아냅니다",
                     font=ctk.CTkFont(size=13), text_color="gray70").pack(pady=(0, 10))

        # ---- 저장 위치 ----
        dir_frame = ctk.CTkFrame(self, fg_color="transparent")
        dir_frame.pack(fill="x", padx=30, pady=(0, 8))
        self.dir_label = ctk.CTkLabel(
            dir_frame, text=self._dir_text(),
            font=ctk.CTkFont(size=12), text_color="gray70",
            anchor="w", wraplength=360, justify="left")
        self.dir_label.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.dir_btn = ctk.CTkButton(
            dir_frame, text="📁 저장 위치", width=110,
            command=self.choose_output_dir)
        self.dir_btn.grid(row=0, column=1)
        dir_frame.grid_columnconfigure(0, weight=1)

        # ---- 형식 선택 ----
        fmt_frame = ctk.CTkFrame(self, fg_color="transparent")
        fmt_frame.pack(pady=(0, 10))
        ctk.CTkLabel(fmt_frame, text="출력 형식:",
                     font=ctk.CTkFont(size=13)).grid(row=0, column=0, padx=(0, 10))
        self.format_var = ctk.StringVar(value="mp3")
        self.format_menu = ctk.CTkOptionMenu(
            fmt_frame, values=list(FORMAT_OPTIONS.keys()),
            variable=self.format_var, width=120)
        self.format_menu.grid(row=0, column=1)

        # ---- 드롭 영역 ----
        self.drop_frame = ctk.CTkFrame(
            self, height=140, corner_radius=16,
            border_width=2, border_color="gray40", fg_color="gray17")
        self.drop_frame.pack(fill="x", padx=30, pady=6)
        self.drop_frame.pack_propagate(False)
        self.drop_label = ctk.CTkLabel(
            self.drop_frame,
            text="⬇  여기에 영상 파일을 드롭하세요\n\n(mp4, mkv, mov, avi, webm, flv)",
            font=ctk.CTkFont(size=15), justify="center")
        self.drop_label.pack(expand=True)

        # ---- 상태 / 진행 ----
        self.progress = ctk.CTkProgressBar(self, height=14, corner_radius=8)
        self.progress.set(0)
        self.progress.pack(fill="x", padx=30, pady=(16, 4))
        self.status_label = ctk.CTkLabel(
            self, text="대기 중 — 영상을 드롭하면 시작합니다.",
            font=ctk.CTkFont(size=13), wraplength=480)
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

        # ---- 드롭 등록 ----
        self.drop_target_register(DND_FILES)
        self.dnd_bind("<<Drop>>", self.on_drop)

    # ---- 저장 위치 표시/선택 ----
    def _dir_text(self):
        return "저장 위치: " + self.output_dir

    def choose_output_dir(self):
        if self.is_processing:
            self.set_status("처리 중에는 저장 위치를 바꿀 수 없어요.")
            return
        folder = filedialog.askdirectory(
            title="결과를 저장할 폴더 선택",
            initialdir=self.output_dir if os.path.isdir(self.output_dir) else os.path.expanduser("~"))
        if folder:
            self.output_dir = folder
            self.dir_label.configure(text=self._dir_text())

    def on_drop(self, event):
        if self.is_processing:
            self.set_status("이미 처리 중이에요. 잠시만 기다려주세요.")
            return
        files = self.tk.splitlist(event.data)
        videos = [f for f in files if f.lower().endswith(SUPPORTED_VIDEO)]
        if not videos:
            self.set_status("지원하지 않는 형식이에요. (mp4, mkv, mov 등)")
            return
        threading.Thread(target=self.extract_all, args=(videos,), daemon=True).start()

    def extract_all(self, videos):
        self.is_processing = True
        self.last_output = None
        self.after(0, lambda: self.open_btn.configure(state="disabled"))
        fmt = self.format_var.get()
        total = len(videos)
        out_dir = self.output_dir   # 이번 작업에 사용할 폴더 고정

        try:
            os.makedirs(out_dir, exist_ok=True)
            for i, video in enumerate(videos, 1):
                name = os.path.basename(video)
                self.set_status(f"[{i}/{total}] 추출 중...  {name}")
                self.set_progress((i - 1) / total)

                out_name = os.path.splitext(name)[0] + "." + fmt
                out_path = os.path.join(out_dir, out_name)

                cmd = ["ffmpeg", "-y", "-i", video] + FORMAT_OPTIONS[fmt] + [out_path]

                creationflags = 0
                startupinfo = None
                if os.name == "nt":
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    creationflags = subprocess.CREATE_NO_WINDOW

                result = subprocess.run(
                    cmd, capture_output=True, text=True,
                    encoding="utf-8", errors="replace",
                    startupinfo=startupinfo, creationflags=creationflags)


                if result.returncode != 0:
                    self.set_status(f"오류 ({name}):\n{result.stderr[-300:]}")
                    self.set_progress(0)
                    return

            self.last_output = out_dir
            self.set_progress(1.0)
            self.set_status(f"✅ 완료!  {total}개 파일을 추출했습니다.\n{out_dir}")
            self.after(0, lambda: self.open_btn.configure(state="normal"))

        except FileNotFoundError:
            self.set_status("ffmpeg를 찾을 수 없어요. 'winget install ffmpeg' 확인 후 cmd를 다시 여세요.")
            self.set_progress(0)
        except Exception as e:
            self.set_status(f"오류: {e}")
            self.set_progress(0)
        finally:
            self.is_processing = False

    # ---- 유틸 ----
    def set_status(self, text):
        self.after(0, lambda: self.status_label.configure(text=text))

    def set_progress(self, value):
        self.after(0, lambda: self.progress.set(value))

    def open_output(self):
        if self.last_output and os.path.isdir(self.last_output):
            os.startfile(self.last_output)

    def reset(self):
        if self.is_processing:
            return
        self.progress.set(0)
        self.last_output = None
        self.open_btn.configure(state="disabled")
        self.set_status("대기 중 — 영상을 드롭하면 시작합니다.")


if __name__ == "__main__":
    App().mainloop()
