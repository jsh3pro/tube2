# -*- coding: utf-8 -*-
"""
Git Auto (add -> commit -> push) GUI Tool
- Python + tkinter GUI
- 대상 폴더 지정/변경 + 기억 (config)
- git status 화면 출력 (길면 로그로)
- 커밋 메시지 직접 입력 + 비우면 디폴트(날짜/시각)
- 브랜치 드롭다운 선택 (디폴트 main, 없으면 현재 브랜치)
- 로그: 저장소 밖 C:\\bin\\git_auto_logs\\<저장소이름>\\<타임스탬프>.log
"""

import os
import sys
import json
import subprocess
from datetime import datetime

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

# ---------------- 설정값 ----------------
DEFAULT_REPO = r"C:\bin\tube2"
LOG_ROOT = r"C:\bin\git_auto_logs"          # 로그는 저장소 밖 (B안)
CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "git_auto.config"
)
STATUS_SCREEN_LIMIT = 15                      # 화면에 보여줄 status 최대 줄 수


# ---------------- 공통 함수 ----------------
def load_config():
    """마지막으로 쓴 대상 폴더를 기억해서 불러옴."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"repo": DEFAULT_REPO}


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def run_git(args, cwd):
    """git 명령 실행 -> (성공여부, 출력텍스트)."""
    try:
        proc = subprocess.run(
            ["git", "-c", "core.quotepath=false"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode == 0, out.strip()
    except FileNotFoundError:
        return False, "git 실행 파일을 찾을 수 없습니다. Git 설치 여부를 확인하세요."
    except Exception as e:
        return False, f"git 실행 오류: {e}"


def is_git_repo(path):
    if not path or not os.path.isdir(path):
        return False
    ok, _ = run_git(["rev-parse", "--is-inside-work-tree"], path)
    return ok


def get_log_path(repo):
    """저장소 밖(B안)에 저장소 이름별 하위 폴더로 로그 경로 생성."""
    repo_name = os.path.basename(os.path.normpath(repo)) or "unknown"
    log_dir = os.path.join(LOG_ROOT, repo_name)
    os.makedirs(log_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(log_dir, f"{stamp}.log")


def write_log(repo, content):
    path = get_log_path(repo)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path
    except Exception as e:
        return f"(로그 저장 실패: {e})"


# ---------------- GUI ----------------
class GitAutoApp:
    def __init__(self, root):
        self.root = root
        self.cfg = load_config()

        root.title("Git Auto - add / commit / push")
        root.geometry("640x560")

        pad = {"padx": 8, "pady": 4}

        # --- 대상 폴더 ---
        frm_repo = ttk.LabelFrame(root, text="1. 대상 폴더 (저장소)")
        frm_repo.pack(fill="x", **pad)

        self.repo_var = tk.StringVar(value=self.cfg.get("repo", DEFAULT_REPO))
        ttk.Entry(frm_repo, textvariable=self.repo_var).pack(
            side="left", fill="x", expand=True, padx=6, pady=6
        )
        ttk.Button(frm_repo, text="폴더 선택", command=self.choose_folder).pack(
            side="left", padx=6
        )
        ttk.Button(frm_repo, text="불러오기/확인", command=self.load_repo).pack(
            side="left", padx=6
        )

        # --- 브랜치 ---
        frm_br = ttk.LabelFrame(root, text="2. 브랜치 선택 (디폴트 main)")
        frm_br.pack(fill="x", **pad)
        self.branch_var = tk.StringVar()
        self.branch_combo = ttk.Combobox(
            frm_br, textvariable=self.branch_var, state="readonly"
        )
        self.branch_combo.pack(side="left", fill="x", expand=True, padx=6, pady=6)
        ttk.Button(frm_br, text="새로고침", command=self.refresh_branches).pack(
            side="left", padx=6
        )

        # --- 커밋 메시지 ---
        frm_msg = ttk.LabelFrame(root, text="3. 커밋 메시지 (비우면 자동 날짜/시각)")
        frm_msg.pack(fill="x", **pad)
        self.msg_var = tk.StringVar()
        ttk.Entry(frm_msg, textvariable=self.msg_var).pack(
            fill="x", expand=True, padx=6, pady=6
        )

        # --- 실행 버튼 ---
        frm_btn = ttk.Frame(root)
        frm_btn.pack(fill="x", **pad)
        ttk.Button(frm_btn, text="status 보기", command=self.show_status).pack(
            side="left", padx=6
        )
        ttk.Button(
            frm_btn, text="실행 (add → commit → push)", command=self.run_all
        ).pack(side="left", padx=6)

        # --- 출력창 ---
        frm_out = ttk.LabelFrame(root, text="출력")
        frm_out.pack(fill="both", expand=True, **pad)
        self.output = scrolledtext.ScrolledText(frm_out, height=12, wrap="word")
        self.output.pack(fill="both", expand=True, padx=6, pady=6)

        # 시작 시 자동 확인
        self.load_repo()

    # ---------- 유틸 ----------
    def log_out(self, text):
        self.output.insert("end", text + "\n")
        self.output.see("end")

    def current_repo(self):
        return self.repo_var.get().strip()

    # ---------- 동작 ----------
    def choose_folder(self):
        init = self.current_repo() if os.path.isdir(self.current_repo()) else LOG_ROOT
        path = filedialog.askdirectory(title="Git 저장소 폴더 선택", initialdir=init)
        if path:
            self.repo_var.set(os.path.normpath(path))
            self.load_repo()

    def load_repo(self):
        repo = self.current_repo()
        if not repo:
            messagebox.showwarning("확인", "대상 폴더를 반드시 지정해 주세요.")
            return
        if not os.path.isdir(repo):
            messagebox.showerror("오류", f"폴더가 존재하지 않습니다:\n{repo}")
            return
        if not is_git_repo(repo):
            messagebox.showerror(
                "오류", f"이 폴더는 git 저장소가 아닙니다:\n{repo}"
            )
            return
        self.cfg["repo"] = repo
        save_config(self.cfg)
        self.log_out(f"[대상 폴더] {repo}")
        self.refresh_branches()

    def refresh_branches(self):
        repo = self.current_repo()
        if not is_git_repo(repo):
            return
        ok, out = run_git(["branch", "--format=%(refname:short)"], repo)
        if not ok:
            self.log_out(f"[브랜치 조회 실패] {out}")
            return
        branches = [b.strip() for b in out.splitlines() if b.strip()]
        if not branches:
            self.log_out("[알림] 브랜치가 없습니다 (커밋이 아직 없을 수 있음).")
            return

        # 현재 브랜치
        ok2, cur = run_git(["branch", "--show-current"], repo)
        cur = cur.strip() if ok2 else ""

        self.branch_combo["values"] = branches

        # 디폴트: main > 현재 브랜치 > 첫 번째
        if "main" in branches:
            default = "main"
        elif cur in branches:
            default = cur
        else:
            default = branches[0]
        self.branch_var.set(default)
        self.log_out(f"[브랜치] {', '.join(branches)} (선택: {default})")

    def show_status(self):
        repo = self.current_repo()
        if not is_git_repo(repo):
            messagebox.showerror("오류", "먼저 올바른 git 저장소를 지정하세요.")
            return
        ok, out = run_git(["status", "-s"], repo)
        if not out:
            self.log_out("[status] 변경 사항이 없습니다.")
            return

        lines = out.splitlines()
        self.log_out(f"[status] 변경 {len(lines)}건")

        if len(lines) <= STATUS_SCREEN_LIMIT:
            for ln in lines:
                self.log_out("  " + ln)
        else:
            # 길면 앞부분만 화면에, 전체는 로그 파일로
            for ln in lines[:STATUS_SCREEN_LIMIT]:
                self.log_out("  " + ln)
            log_path = write_log(repo, out)
            self.log_out(
                f"  ...외 {len(lines) - STATUS_SCREEN_LIMIT}건 생략. "
                f"전체는 로그 참조:\n  {log_path}"
            )

    def run_all(self):
        repo = self.current_repo()
        if not is_git_repo(repo):
            messagebox.showerror("오류", "먼저 올바른 git 저장소를 지정하세요.")
            return

        branch = self.branch_var.get().strip()
        if not branch:
            messagebox.showwarning("확인", "push할 브랜치를 선택하세요.")
            return

        # 커밋 메시지 (비우면 디폴트)
        msg = self.msg_var.get().strip()
        if not msg:
            msg = "Update: " + datetime.now().strftime("%Y-%m-%d %H:%M") + " (자동 커밋)"
            self.log_out(f"[커밋 메시지] 디폴트 사용 → {msg}")

        # 변경 사항 확인
        ok, st = run_git(["status", "-s"], repo)
        if not st:
            messagebox.showinfo("알림", "변경 사항이 없어 커밋할 내용이 없습니다.")
            self.log_out("[중단] 변경 사항 없음.")
            return

        # push 전 최종 확인
        if not messagebox.askyesno(
            "최종 확인",
            f"저장소: {repo}\n브랜치: {branch}\n메시지: {msg}\n\npush까지 진행할까요?",
        ):
            self.log_out("[취소] 사용자가 중단했습니다.")
            return

        log_buffer = [f"=== Git Auto 실행 {datetime.now()} ===",
                      f"repo: {repo}", f"branch: {branch}", f"message: {msg}", ""]

        # 1) add
        self.log_out("① git add .")
        ok, out = run_git(["add", "."], repo)
        log_buffer += ["[add]", out]
        if not ok:
            self.log_out(f"  실패: {out}")
            write_log(repo, "\n".join(log_buffer))
            return

        # 2) commit
        self.log_out("② git commit")
        ok, out = run_git(["commit", "-m", msg], repo)
        log_buffer += ["[commit]", out]
        self.log_out("  " + out.splitlines()[0] if out else "  완료")
        if not ok:
            self.log_out(f"  실패: {out}")
            write_log(repo, "\n".join(log_buffer))
            return

        # 3) push (upstream 자동 설정 포함)
        self.log_out(f"③ git push origin {branch}")
        ok, out = run_git(["push", "-u", "origin", branch], repo)
        log_buffer += ["[push]", out]
        if ok:
            self.log_out("  ✅ push 완료")
        else:
            self.log_out(f"  ❌ push 실패: {out}")

        log_path = write_log(repo, "\n".join(log_buffer))
        self.log_out(f"[로그 저장] {log_path}")


def main():
    root = tk.Tk()
    GitAutoApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
