# -*- coding: utf-8 -*-
"""
Git Auto (pull / add -> commit -> push / clone) GUI Tool
- Python + tkinter GUI
- 1~3: 기존 저장소 pull / add / commit / push (변경 없음)
- 4: 클론 (독립 영역) - 기존 폴더 보호
    * 원격 URL, 클론 전용 위치(위쪽과 별개), 디폴트 임시폴더
    * 클론 위치에 이미 git 저장소가 있으면 경고 후 중단
    * 위쪽 대상폴더와 같은 경로면 중단
    * 폴더가 비어있지 않으면 확인
- 로그: 저장소 밖 C:\\bin\\git_auto_logs\\<이름>\\<타임스탬프>.log
- 한글 파일명 표시: core.quotepath=false
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
LOG_ROOT = r"C:\bin\git_auto_logs"           # 로그는 저장소 밖 (B안)
CLONE_TEMP_ROOT = r"C:\bin\git_clone_temp"   # 클론 임시 기본 위치
CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "git_auto.config"
)
STATUS_SCREEN_LIMIT = 15                      # 화면에 보여줄 status 최대 줄 수


# ---------------- 공통 함수 ----------------
def load_config():
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


def run_git(args, cwd=None):
    """git 명령 실행 -> (성공여부, 출력텍스트). cwd=None이면 clone 등 상위에서 실행."""
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


def has_git_dir(path):
    """폴더 안에 .git 이 있는지(=이미 저장소인지) 검사. 폴더 없으면 False."""
    if not path or not os.path.isdir(path):
        return False
    return os.path.isdir(os.path.join(path, ".git")) or is_git_repo(path)


def get_log_path(name):
    safe = name or "unknown"
    log_dir = os.path.join(LOG_ROOT, safe)
    os.makedirs(log_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(log_dir, f"{stamp}.log")


def write_log(name, content):
    path = get_log_path(name)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path
    except Exception as e:
        return f"(로그 저장 실패: {e})"


def repo_name_from_url(url):
    """원격 URL에서 저장소 이름 추출 (.../foo.git -> foo)."""
    base = url.rstrip("/").split("/")[-1]
    if base.endswith(".git"):
        base = base[:-4]
    return base or "cloned_repo"


# ---------------- GUI ----------------
class GitAutoApp:
    def __init__(self, root):
        self.root = root
        self.cfg = load_config()

        root.title("Git Auto - pull / add / commit / push / clone")
        root.geometry("660x680")

        pad = {"padx": 8, "pady": 4}

        # --- 1. 대상 폴더 ---
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

        # --- 2. 브랜치 ---
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

        # --- 3. 커밋 메시지 ---
        frm_msg = ttk.LabelFrame(root, text="3. 커밋 메시지 (비우면 자동 날짜/시각)")
        frm_msg.pack(fill="x", **pad)
        self.msg_var = tk.StringVar()
        ttk.Entry(frm_msg, textvariable=self.msg_var).pack(
            fill="x", expand=True, padx=6, pady=6
        )

        # --- 실행 버튼 (pull / status / 실행) ---
        frm_btn = ttk.Frame(root)
        frm_btn.pack(fill="x", **pad)
        ttk.Button(
            frm_btn, text="서버→로컬 가져오기(pull)", command=self.pull_from_server
        ).pack(side="left", padx=6)
        ttk.Button(frm_btn, text="status 보기", command=self.show_status).pack(
            side="left", padx=6
        )
        ttk.Button(
            frm_btn, text="실행 (add → commit → push)", command=self.run_all
        ).pack(side="left", padx=6)

        # --- 4. 클론 (독립 영역) ---
        frm_clone = ttk.LabelFrame(root, text="4. 클론 (기존 폴더와 분리 / 임시)")
        frm_clone.pack(fill="x", **pad)

        row1 = ttk.Frame(frm_clone)
        row1.pack(fill="x", padx=6, pady=3)
        ttk.Label(row1, text="원격 URL:", width=10).pack(side="left")
        self.clone_url_var = tk.StringVar(value=self.cfg.get("clone_url", ""))
        ttk.Entry(row1, textvariable=self.clone_url_var).pack(
            side="left", fill="x", expand=True, padx=4
        )

        row2 = ttk.Frame(frm_clone)
        row2.pack(fill="x", padx=6, pady=3)
        ttk.Label(row2, text="클론 위치:", width=10).pack(side="left")
        self.clone_dir_var = tk.StringVar(
            value=self.cfg.get("clone_dir", CLONE_TEMP_ROOT)
        )
        ttk.Entry(row2, textvariable=self.clone_dir_var).pack(
            side="left", fill="x", expand=True, padx=4
        )
        ttk.Button(row2, text="위치 선택", command=self.choose_clone_dir).pack(
            side="left", padx=4
        )

        row3 = ttk.Frame(frm_clone)
        row3.pack(fill="x", padx=6, pady=3)
        ttk.Button(row3, text="클론 실행", command=self.run_clone).pack(side="left")
        ttk.Label(
            row3, text="  ※ 임시 폴더로 받아 검토 후 반영하세요.", foreground="gray"
        ).pack(side="left")

        # --- 출력창 ---
        frm_out = ttk.LabelFrame(root, text="출력")
        frm_out.pack(fill="both", expand=True, **pad)
        self.output = scrolledtext.ScrolledText(frm_out, height=10, wrap="word")
        self.output.pack(fill="both", expand=True, padx=6, pady=6)

        self.load_repo()

    # ---------- 유틸 ----------
    def log_out(self, text):
        self.output.insert("end", text + "\n")
        self.output.see("end")

    def current_repo(self):
        return self.repo_var.get().strip()

    # ---------- 대상 폴더 / 브랜치 ----------
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
            messagebox.showerror("오류", f"이 폴더는 git 저장소가 아닙니다:\n{repo}")
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
        ok2, cur = run_git(["branch", "--show-current"], repo)
        cur = cur.strip() if ok2 else ""
        self.branch_combo["values"] = branches
        if "main" in branches:
            default = "main"
        elif cur in branches:
            default = cur
        else:
            default = branches[0]
        self.branch_var.set(default)
        self.log_out(f"[브랜치] {', '.join(branches)} (선택: {default})")

    # ---------- pull ----------
    def pull_from_server(self):
        repo = self.current_repo()
        if not is_git_repo(repo):
            messagebox.showerror("오류", "먼저 올바른 git 저장소를 지정하세요.")
            return
        branch = self.branch_var.get().strip()
        if not branch:
            messagebox.showwarning("확인", "가져올 브랜치를 선택하세요.")
            return
        ok, st = run_git(["status", "-s"], repo)
        if st:
            n = len(st.splitlines())
            if not messagebox.askyesno(
                "로컬 변경 감지 (주의)",
                f"로컬에 아직 커밋하지 않은 변경이 {n}건 있습니다.\n"
                f"대상 폴더: {repo}\n\n"
                "지금 가져오면(pull) 충돌하거나 덮어쓸 수 있습니다.\n\n계속할까요?",
                icon="warning",
            ):
                self.log_out("[취소] 로컬 변경이 있어 가져오기를 중단했습니다.")
                return
        if not messagebox.askyesno(
            "가져오기 확인",
            f"저장소: {repo}\n브랜치: {branch}\n\n서버 → 로컬로 가져올까요?",
        ):
            self.log_out("[취소] 사용자가 가져오기를 중단했습니다.")
            return
        name = os.path.basename(os.path.normpath(repo))
        log_buffer = [f"=== Git Pull {datetime.now()} ===",
                      f"repo: {repo}", f"branch: {branch}", ""]
        self.log_out(f"⬇ git pull origin {branch}")
        ok, out = run_git(["pull", "origin", branch], repo)
        log_buffer += ["[pull]", out]
        if ok:
            self.log_out("  ✅ 가져오기 완료")
            for ln in out.splitlines()[:STATUS_SCREEN_LIMIT]:
                self.log_out("  " + ln)
        else:
            self.log_out(f"  ❌ 가져오기 실패: {out}")
        self.log_out(f"[로그 저장] {write_log(name, chr(10).join(log_buffer))}")
        self.refresh_branches()

    # ---------- status ----------
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
        name = os.path.basename(os.path.normpath(repo))
        if len(lines) <= STATUS_SCREEN_LIMIT:
            for ln in lines:
                self.log_out("  " + ln)
        else:
            for ln in lines[:STATUS_SCREEN_LIMIT]:
                self.log_out("  " + ln)
            log_path = write_log(name, out)
            self.log_out(
                f"  ...외 {len(lines) - STATUS_SCREEN_LIMIT}건 생략. "
                f"전체는 로그 참조:\n  {log_path}"
            )

    # ---------- add/commit/push ----------
    def run_all(self):
        repo = self.current_repo()
        if not is_git_repo(repo):
            messagebox.showerror("오류", "먼저 올바른 git 저장소를 지정하세요.")
            return
        branch = self.branch_var.get().strip()
        if not branch:
            messagebox.showwarning("확인", "push할 브랜치를 선택하세요.")
            return
        msg = self.msg_var.get().strip()
        if not msg:
            msg = "Update: " + datetime.now().strftime("%Y-%m-%d %H:%M") + " (자동 커밋)"
            self.log_out(f"[커밋 메시지] 디폴트 사용 → {msg}")
        ok, st = run_git(["status", "-s"], repo)
        if not st:
            messagebox.showinfo("알림", "변경 사항이 없어 커밋할 내용이 없습니다.")
            self.log_out("[중단] 변경 사항 없음.")
            return
        if not messagebox.askyesno(
            "최종 확인",
            f"저장소: {repo}\n브랜치: {branch}\n메시지: {msg}\n\npush까지 진행할까요?",
        ):
            self.log_out("[취소] 사용자가 중단했습니다.")
            return
        name = os.path.basename(os.path.normpath(repo))
        log_buffer = [f"=== Git Auto {datetime.now()} ===",
                      f"repo: {repo}", f"branch: {branch}", f"message: {msg}", ""]
        self.log_out("① git add .")
        ok, out = run_git(["add", "."], repo)
        log_buffer += ["[add]", out]
        if not ok:
            self.log_out(f"  실패: {out}")
            write_log(name, chr(10).join(log_buffer))
            return
        self.log_out("② git commit")
        ok, out = run_git(["commit", "-m", msg], repo)
        log_buffer += ["[commit]", out]
        self.log_out("  " + (out.splitlines()[0] if out else "완료"))
        if not ok:
            self.log_out(f"  실패: {out}")
            write_log(name, chr(10).join(log_buffer))
            return
        self.log_out(f"③ git push origin {branch}")
        ok, out = run_git(["push", "-u", "origin", branch], repo)
        log_buffer += ["[push]", out]
        self.log_out("  ✅ push 완료" if ok else f"  ❌ push 실패: {out}")
        self.log_out(f"[로그 저장] {write_log(name, chr(10).join(log_buffer))}")

    # ---------- 4. 클론 ----------
    def choose_clone_dir(self):
        init = (
            self.clone_dir_var.get().strip()
            if os.path.isdir(self.clone_dir_var.get().strip())
            else CLONE_TEMP_ROOT
        )
        path = filedialog.askdirectory(title="클론 받을 위치 선택", initialdir=init)
        if path:
            self.clone_dir_var.set(os.path.normpath(path))

    def run_clone(self):
        url = self.clone_url_var.get().strip()
        base_dir = self.clone_dir_var.get().strip()

        if not url:
            messagebox.showwarning("확인", "원격 URL을 입력하세요.")
            return
        if not base_dir:
            messagebox.showwarning("확인", "클론 받을 위치를 지정하세요.")
            return

        # 최종 클론 대상 폴더 = 위치 + 저장소이름
        name = repo_name_from_url(url)
        target = os.path.normpath(os.path.join(base_dir, name))

        # 안전장치 1) 위쪽 대상 폴더와 같은 경로 금지 (기존 폴더 보호)
        repo = os.path.normpath(self.current_repo()) if self.current_repo() else ""
        if repo and os.path.abspath(target).lower() == os.path.abspath(repo).lower():
            messagebox.showerror(
                "중단 (기존 폴더 보호)",
                f"클론 위치가 위쪽 대상 폴더와 같습니다:\n{target}\n\n"
                "기존 폴더 보호를 위해 다른 위치를 지정하세요.",
            )
            return

        # 안전장치 2) 이미 git 저장소가 있으면 경고 후 중단 (요청 사항)
        if has_git_dir(target):
            messagebox.showwarning(
                "중단 (이미 git 저장소 존재)",
                f"클론 위치에 이미 git 저장소가 있습니다:\n{target}\n\n"
                "기존 저장소를 보호하기 위해 클론을 진행하지 않습니다.\n"
                "다른 위치를 지정하거나, 최신화는 pull을 사용하세요.",
                icon="warning",
            )
            self.log_out(f"[클론 중단] 이미 git 저장소 존재: {target}")
            return

        # 안전장치 3) 폴더가 비어있지 않으면 확인
        if os.path.isdir(target) and os.listdir(target):
            if not messagebox.askyesno(
                "확인 (폴더가 비어있지 않음)",
                f"클론 위치에 이미 파일이 있습니다:\n{target}\n\n"
                "clone이 실패하거나 섞일 수 있습니다. 계속할까요?",
                icon="warning",
            ):
                self.log_out("[클론 취소] 폴더가 비어있지 않음.")
                return

        if not messagebox.askyesno(
            "클론 확인",
            f"원격: {url}\n클론 위치: {target}\n\n클론을 진행할까요?",
        ):
            self.log_out("[클론 취소] 사용자가 중단했습니다.")
            return

        # 실행
        os.makedirs(base_dir, exist_ok=True)
        self.cfg["clone_url"] = url
        self.cfg["clone_dir"] = base_dir
        save_config(self.cfg)

        log_buffer = [f"=== Git Clone {datetime.now()} ===",
                      f"url: {url}", f"target: {target}", ""]
        self.log_out(f"⧉ git clone → {target}")
        ok, out = run_git(["clone", url, target])   # cwd=None (상위에서 실행)
        log_buffer += ["[clone]", out]
        if ok:
            self.log_out("  ✅ 클론 완료")
            for ln in out.splitlines()[:STATUS_SCREEN_LIMIT]:
                self.log_out("  " + ln)
            self.log_out(f"  → 임시 폴더에서 내용을 검토한 뒤 반영하세요: {target}")
        else:
            self.log_out(f"  ❌ 클론 실패: {out}")
        self.log_out(f"[로그 저장] {write_log(name, chr(10).join(log_buffer))}")


def main():
    root = tk.Tk()
    GitAutoApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
