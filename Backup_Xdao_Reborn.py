import tkinter as tk
from tkinter import messagebox, filedialog, ttk
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import os
import json
import threading
import time
import re
import zipfile
import shutil
import sys
import webbrowser
import glob
import datetime
from urllib.parse import urlparse

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# 全局配置
BASE_DIR = get_base_dir()
DEFAULT_SAVE_SUBDIR = "离线内容"
CONFIG_FILE = os.path.join(BASE_DIR, "user_config.json")

# 字体配置
FONT_NORMAL = ("Microsoft YaHei UI", 9)
FONT_BOLD = ("Microsoft YaHei UI", 9, "bold")

# 默认UA
DEFAULT_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

CHECK_URL = "https://www.nmbxd1.com/f/%E6%95%85%E4%BA%8B" 
AUTH_FAILURE_TEXT = "必须登入领取饼干后才可以访问"
GITHUB_URL = "https://github.com/GooPigeon/XDDownload"

class ForumBackupApp:
    def __init__(self, root):
        self.root = root
        self.root.title("X岛离线备份 Reborn") 
        self.root.geometry("680x600")
        self.root.minsize(680, 600)

        # === 优化1: 初始化 Session 并配置重试机制 ===
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': DEFAULT_UA})
        
        # 配置重试策略：重试3次，针对 500, 502, 503, 504 错误
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

        try:
            icon_path = resource_path('logo.ico')
            self.root.iconbitmap(icon_path)
        except Exception:
            pass 

        style = ttk.Style()
        try: style.theme_use('vista')
        except: style.theme_use('clam')

        self.thread_id_var = tk.StringVar()
        self.start_page_var = tk.StringVar(value="1")
        self.save_path_var = tk.StringVar(value=os.path.join(BASE_DIR, DEFAULT_SAVE_SUBDIR))
        self.format_var = tk.StringVar(value="仅保存文件夹")
        
        self.hash_display_var = tk.StringVar() 
        self.hash_status_var = tk.StringVar(value="等待检查") 
        self.status_text_var = tk.StringVar(value="等待操作...") 
        self.is_editing_var = tk.BooleanVar(value=False) 
        
        self.current_state = "INIT" 
        
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.is_running = False

        self.setup_ui()
        self.root.after(100, self.initial_load) 

    def setup_ui(self):
        # 1. Userhash 区域
        frame_hash_container = ttk.LabelFrame(self.root, text=" Userhash (饼干) 管理 ", padding=(10, 5))
        frame_hash_container.pack(fill="x", padx=10, pady=5)
        
        frame_hash_inner = ttk.Frame(frame_hash_container)
        frame_hash_inner.pack(fill="x")
        
        self.lbl_status = ttk.Label(frame_hash_inner, textvariable=self.hash_status_var, 
                                    font=FONT_BOLD, foreground="gray", width=12, anchor="center")
        self.lbl_status.grid(row=0, column=0, padx=(0, 10))
        
        self.entry_hash = ttk.Entry(frame_hash_inner, textvariable=self.hash_display_var, width=45)
        self.entry_hash.grid(row=0, column=1, sticky="ew", padx=5)
        self.entry_hash.bind("<Button-1>", self.on_entry_click)
        self.entry_hash.bind("<FocusOut>", self.on_focus_out)
        
        self.frame_hash_ops = ttk.Frame(frame_hash_inner)
        self.frame_hash_ops.grid(row=0, column=2, padx=(5, 0))
        
        self.btn_save_hash = ttk.Button(self.frame_hash_ops, text="保存", command=self.action_save_hash, width=6)
        self.chk_edit = ttk.Checkbutton(self.frame_hash_ops, text="修改", variable=self.is_editing_var, 
                                        command=self.on_edit_check_toggle)

        frame_hash_inner.columnconfigure(1, weight=1)

        # 2. 任务信息区域
        frame_id = ttk.LabelFrame(self.root, text=" 任务信息 ", padding=(10, 5))
        frame_id.pack(fill="x", padx=10, pady=5)
        
        frame_id_row1 = ttk.Frame(frame_id)
        frame_id_row1.pack(fill="x", pady=2)
        
        ttk.Label(frame_id_row1, text="串号:", font=FONT_NORMAL).pack(side=tk.LEFT)
        ttk.Entry(frame_id_row1, textvariable=self.thread_id_var, width=15).pack(side=tk.LEFT, padx=(5, 10))
        
        self.btn_check_status = ttk.Button(frame_id_row1, text="检查访问权限/更新/下载状态", command=self.run_check_status_thread)
        self.btn_check_status.pack(side=tk.LEFT, fill="x", expand=True, padx=(0, 5))

        self.btn_batch_update = ttk.Button(frame_id_row1, text="一键更新已备份", command=self.run_batch_update_thread)
        self.btn_batch_update.pack(side=tk.LEFT, fill="x", expand=True)

        frame_id_row2 = ttk.Frame(frame_id)
        frame_id_row2.pack(fill="x", pady=5)
        
        ttk.Label(frame_id_row2, text="从第", font=FONT_NORMAL).pack(side=tk.LEFT)
        ttk.Entry(frame_id_row2, textvariable=self.start_page_var, width=5, justify="center").pack(side=tk.LEFT, padx=2)
        ttk.Label(frame_id_row2, text="页开始下载", font=FONT_NORMAL).pack(side=tk.LEFT)
        
        ttk.Label(frame_id_row2, textvariable=self.status_text_var, foreground="black", font=FONT_NORMAL).pack(side=tk.RIGHT)

        self.progress_bar = ttk.Progressbar(frame_id, mode="determinate")
        self.progress_bar.pack(fill="x", pady=(2, 5))

        # 3. 保存位置
        frame_path = ttk.LabelFrame(self.root, text=" 保存位置 ", padding=(10, 5))
        frame_path.pack(fill="x", padx=10, pady=5)
        ttk.Entry(frame_path, textvariable=self.save_path_var).pack(side=tk.LEFT, fill="x", expand=True)
        ttk.Button(frame_path, text="浏览...", command=self.choose_directory).pack(side=tk.LEFT, padx=5)

        # 4. 底部控制区
        frame_action = ttk.Frame(self.root, padding=(10, 10))
        frame_action.pack(fill="x", padx=10)
        
        self.btn_github = ttk.Button(frame_action, text="GitHub 仓库", command=self.open_github_link, width=12)
        self.btn_github.pack(side=tk.LEFT, padx=(0, 15))

        ttk.Label(frame_action, text="保存形式:").pack(side=tk.LEFT)
        self.combo_format = ttk.Combobox(frame_action, textvariable=self.format_var, state="readonly", width=16)
        self.combo_format['values'] = ("仅保存文件夹", "仅保存为压缩包", "文件夹+压缩包")
        self.combo_format.pack(side=tk.LEFT, padx=5)
        
        self.btn_start = ttk.Button(frame_action, text="开始备份", command=self.toggle_start_stop)
        self.btn_start.pack(side=tk.RIGHT)
        self.btn_pause = ttk.Button(frame_action, text="暂停", command=self.toggle_pause, state="disabled")
        self.btn_pause.pack(side=tk.RIGHT, padx=5)

        # 5. 日志
        self.log_text = tk.Text(self.root, height=8, bg="#F9F9F9", fg="black", font=FONT_NORMAL, state="disabled")
        self.log_text.pack(fill="both", expand=True, padx=10, pady=5)

    def open_github_link(self):
        webbrowser.open(GITHUB_URL)

    # === 工具：文件名净化 ===
    def sanitize_filename(self, filename):
        return re.sub(r'[\\/*?:"<>|]', "", filename)

    def get_local_max_page(self, target_dir):
        local_max = 0
        if os.path.exists(target_dir):
            files = glob.glob(os.path.join(target_dir, "page_*.html"))
            if files:
                pages = []
                for f in files:
                    try:
                        num = int(re.search(r'page_(\d+).html', f).group(1))
                        pages.append(num)
                    except: pass
                if pages: local_max = max(pages)
        return local_max

    def handle_thread_status(self, tid, target_dir, resp_text, resp_status):
        status_code = 0
        status_str = "正常"
        base_path = os.path.dirname(target_dir)
        
        local_page_count = self.get_local_max_page(target_dir)

        suffix = ""
        
        if "主串不存在" in resp_text:
            status_code = 1
            status_str = "回复串"
            suffix = "_回复串"
        elif "该串不存在" in resp_text or resp_status == 404:
            if local_page_count > 0:
                status_code = 3
                status_str = "幸存"
                suffix = "_幸存"
            else:
                status_code = 2
                status_str = "已不存在"
                suffix = "_已不存在"
        else:
            status_code = 0
            status_str = "正常"
            suffix = ""

        new_dir_name = f"{tid}{suffix}"
        new_dir_path = os.path.join(base_path, new_dir_name)
        
        if os.path.normpath(target_dir) != os.path.normpath(new_dir_path):
            if os.path.exists(target_dir) and not os.path.exists(new_dir_path):
                try:
                    os.rename(target_dir, new_dir_path)
                    self.log(f"状态更新：文件夹重命名为 {new_dir_name}")
                    
                    if status_code == 3:
                        self.root.after(0, lambda: messagebox.showinfo("幸存提示", f"串号 {tid}：\n该串已被删除，但检测到本地有备份。\n已标记为“幸存”。"))
                        
                except Exception as e:
                    self.log(f"重命名失败: {e}")
                    new_dir_path = target_dir
            elif os.path.exists(new_dir_path) and os.path.exists(target_dir):
                new_dir_path = target_dir
            else:
                new_dir_path = new_dir_path

        return status_code, status_str, new_dir_path

    # === 检查更新逻辑 ===
    def run_check_status_thread(self):
        threading.Thread(target=self._check_status_logic, daemon=True).start()

    def _check_status_logic(self):
        tid = self.thread_id_var.get().strip()
        base_path = self.save_path_var.get().strip()
        userhash = self.reload_hash_from_file()

        if not tid:
            self.status_text_var.set("请输入串号")
            return
        
        self.btn_check_status.config(state="disabled")
        self.status_text_var.set("正在分析...")
        self.progress_bar['value'] = 0

        try:
            target_dir = os.path.join(base_path, tid)
            possible_dirs = glob.glob(os.path.join(base_path, f"{tid}*"))
            if possible_dirs:
                target_dir = possible_dirs[0]

            local_max_page = self.get_local_max_page(target_dir)
            
            # 使用 Session 发送请求
            self.session.cookies.set('userhash', userhash)
            
            try:
                resp = self.session.get(f"https://www.nmbxd1.com/t/{tid}?page=1", timeout=10)
                resp.encoding = 'utf-8'
            except Exception as e:
                self.status_text_var.set("网络错误")
                self.btn_check_status.config(state="normal")
                return

            status_code, status_str, final_dir = self.handle_thread_status(tid, target_dir, resp.text, resp.status_code)
            
            if status_code == 2 or status_code == 3:
                self.status_text_var.set(f"本地:{local_max_page}页 | 状态:{status_str}")
                self.progress_bar['value'] = 0
                self.btn_check_status.config(state="normal")
                return

            if AUTH_FAILURE_TEXT in resp.text:
                perm_text = "无权限(需饼干)"
            else:
                perm_text = "权限正常"

            match = re.search(r'href="[^"]+page=(\d+)">末页</a>', resp.text)
            online_max_page = int(match.group(1)) if match else 1

            self.status_text_var.set(f"本地:{local_max_page}/在线:{online_max_page} ({status_str}/{perm_text})")
            
            self.progress_bar['maximum'] = online_max_page
            self.progress_bar['value'] = local_max_page

            if local_max_page == 0:
                self.start_page_var.set("1")
            elif local_max_page < online_max_page:
                self.start_page_var.set(str(local_max_page))
            elif local_max_page == online_max_page:
                if messagebox.askyesno("检查结果", "更新内容未超过一页。\n是否重新下载最后一页？"):
                    self.start_page_var.set(str(local_max_page))
                else:
                    self.start_page_var.set(str(online_max_page + 1))
                    self.log("跳过此次更新。")

        except Exception as e:
            self.status_text_var.set("检查出错")
            self.log(f"错误详情: {e}")
        finally:
            self.btn_check_status.config(state="normal")

    # === 一键更新逻辑 (带统计报告) ===
    def run_batch_update_thread(self):
        if messagebox.askyesno("确认", "即将扫描所有已备份的文件夹进行增量更新。\n已标记为[已不存在/回复串/幸存]的将被跳过。\n确定开始吗？"):
            threading.Thread(target=self._batch_update_logic, daemon=True).start()

    def _batch_update_logic(self):
        self.is_running = True
        self.stop_event.clear()
        self.btn_batch_update.config(state="disabled")
        self.btn_check_status.config(state="disabled")
        self.btn_start.config(text="停止")
        
        base_path = self.save_path_var.get().strip()
        userhash = self.reload_hash_from_file()
        
        stats = {"success": 0, "skipped": 0, "failed": 0, "total": 0}

        try:
            if not os.path.exists(base_path):
                self.log("保存目录不存在")
                return
            
            all_dirs = [d for d in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, d))]
            
            update_list = []
            for d in all_dirs:
                if "_已不存在" in d or "_回复串" in d or "_幸存" in d:
                    continue
                match = re.match(r'^(\d+)', d)
                if match:
                    tid = match.group(1)
                    update_list.append(tid)
            
            stats["total"] = len(update_list)
            self.log(f"扫描到 {stats['total']} 个可更新的串，开始处理...")
            
            count = 0
            for tid in update_list:
                if self.stop_event.is_set(): break
                count += 1
                self.log(f"--- 正在处理 ({count}/{len(update_list)}): {tid} ---")
                
                # 调用核心备份逻辑，并获取返回值 True/False
                result = self._perform_backup_task(tid, userhash, base_path, is_batch=True)
                
                if result == "success": stats["success"] += 1
                elif result == "skipped": stats["skipped"] += 1
                else: stats["failed"] += 1
                
                time.sleep(1) 
            
            self.log("=== 批量更新完成 ===")
            
            # 优化3: 弹出统计报告
            report_msg = (
                f"批量更新任务结束！\n\n"
                f"📂 总扫描: {stats['total']} 个\n"
                f"✅ 更新成功: {stats['success']} 个\n"
                f"⏩ 无需更新/跳过: {stats['skipped']} 个\n"
                f"❌ 失败/错误: {stats['failed']} 个"
            )
            messagebox.showinfo("完成", report_msg)

        except Exception as e:
            self.log(f"批量更新出错: {e}")
        finally:
            self.is_running = False
            self.btn_batch_update.config(state="normal")
            self.btn_check_status.config(state="normal")
            self.btn_start.config(text="开始备份")

    # === 核心备份任务 ===
    def _perform_backup_task(self, tid, userhash, base_path, is_batch=False):
        """
        返回状态字符串: "success", "skipped", "failed"
        """
        try:
            target_dir = os.path.join(base_path, tid)
            possible_dirs = glob.glob(os.path.join(base_path, f"{tid}*"))
            if possible_dirs:
                target_dir = possible_dirs[0]

            self.session.cookies.set('userhash', userhash)
            
            try:
                resp = self.session.get(f"https://www.nmbxd1.com/t/{tid}?page=1", timeout=10)
                resp.encoding = 'utf-8'
            except:
                self.log(f"[{tid}] 网络请求失败，跳过")
                return "failed"

            status_code, status_str, target_dir = self.handle_thread_status(tid, target_dir, resp.text, resp.status_code)
            
            if status_code == 2:
                self.log(f"[{tid}] 串已被删除，跳过")
                return "skipped"
            if status_code == 3:
                self.log(f"[{tid}] 串已失效但本地幸存，跳过")
                return "skipped"
            
            if status_code == 1: 
                if is_batch: 
                     self.log(f"[{tid}] 变为回复串，跳过")
                     return "skipped"
            
            assets_dir = os.path.join(target_dir, "assets")
            if not os.path.exists(assets_dir): os.makedirs(assets_dir)

            if AUTH_FAILURE_TEXT in resp.text:
                self.log(f"[{tid}] 需要饼干权限，跳过")
                return "failed"

            match = re.search(r'href="[^"]+page=(\d+)">末页</a>', resp.text)
            online_max_page = int(match.group(1)) if match else 1
            
            local_max_page = self.get_local_max_page(target_dir)
            
            start_page = 1
            if is_batch:
                if local_max_page < online_max_page:
                    start_page = max(1, local_max_page) 
                elif local_max_page == online_max_page:
                    self.log(f"[{tid}] 已是最新，跳过")
                    return "skipped"
            else:
                try:
                    ui_start = int(self.start_page_var.get().strip())
                    start_page = max(1, ui_start)
                except: start_page = 1

            if start_page > online_max_page:
                self.log(f"[{tid}] 起始页大于总页数，跳过")
                return "skipped"

            if not is_batch:
                self.progress_bar['maximum'] = online_max_page
                self.progress_bar['value'] = start_page - 1
            else:
                pass

            for page in range(start_page, online_max_page + 1):
                if self.stop_event.is_set(): return "failed"

                self.log(f"[{tid}] 下载第 {page}/{online_max_page} 页...")
                
                if page == 1 and start_page == 1: html = resp.text
                else:
                    try:
                        r = self.session.get(f"https://www.nmbxd1.com/t/{tid}?page={page}", timeout=10)
                        r.encoding = 'utf-8'
                        if AUTH_FAILURE_TEXT in r.text: return "failed"
                        html = r.text
                    except: continue

                def repl(m): 
                    return f'{m.group(1)}{self.download_asset(m.group(2), assets_dir)}{m.group(3)}'
                
                html = re.sub(r'(<link[^>]+href=["\'])(.*?)(["\'])', repl, html)
                html = re.sub(r'(src=["\'])(.*?)(["\'])', repl, html)
                html = re.sub(r'(url\([\"\']?)(.*?)([\"\']?\))', repl, html)
                html = re.sub(r'href="[^"]*[?&]page=(\d+)"', lambda m: f'href="page_{m.group(1)}.html"', html)
                html = html.replace(f'href="/t/{tid}"', 'href="page_1.html"')
                html = html.replace(f'href="/t/{tid}?page=1"', 'href="page_1.html"')

                with open(os.path.join(target_dir, f"page_{page}.html"), "w", encoding="utf-8") as f:
                    f.write(html)
                
                if not is_batch:
                    self.progress_bar['value'] = page
                
                time.sleep(0.5)

            self.save_backup_info(target_dir, tid, online_max_page, status_str)

            fmt = self.format_var.get()
            if not is_batch and "压缩包" in fmt:
                 self.log(f"[{tid}] 正在压缩...")
                 with zipfile.ZipFile(os.path.join(base_path, f"{tid}.zip"), 'w', zipfile.ZIP_DEFLATED) as z:
                    for r, d, f in os.walk(target_dir):
                        for file in f:
                            z.write(os.path.join(r, file), os.path.relpath(os.path.join(r, file), base_path))
            
            if fmt == "仅保存为压缩包": shutil.rmtree(target_dir)

            return "success"

        except Exception as e:
            self.log(f"[{tid}] 任务出错: {e}")
            return "failed"

    def save_backup_info(self, target_dir, tid, total_pages, status):
        info = {
            "thread_id": tid,
            "total_pages": total_pages,
            "thread_status": status,
            "last_backup_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        try:
            with open(os.path.join(target_dir, "backup_info.json"), "w", encoding="utf-8") as f:
                json.dump(info, f, indent=4, ensure_ascii=False)
        except: pass

    # === 辅助函数 ===
    def initial_load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    saved_hash = config.get('userhash', '').strip()
                    saved_path = config.get('save_path', '')
                    if saved_path and os.path.exists(saved_path):
                        self.save_path_var.set(saved_path)
                    if saved_hash:
                        self.switch_to_hidden(run_check=True)
                    else:
                        self.switch_to_empty()
            except: self.switch_to_empty()
        else: self.switch_to_empty()

    def reload_hash_from_file(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f).get('userhash', '').strip()
        except: pass
        return ""

    def save_config_to_file(self, new_hash):
        config = {'userhash': new_hash, 'save_path': self.save_path_var.get()}
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f: json.dump(config, f)

    def switch_to_empty(self):
        self.current_state = "EMPTY"
        self.hash_display_var.set("")
        self.entry_hash.config(state="normal", foreground="black", justify="left")
        self.chk_edit.pack_forget()
        self.btn_save_hash.pack(side=tk.RIGHT)
        self.hash_status_var.set("未设置")
        self.lbl_status.config(foreground="gray")

    def switch_to_hidden(self, run_check=False):
        self.current_state = "HIDDEN"
        self.is_editing_var.set(False) 
        self.hash_display_var.set("已隐藏 (点击查看)")
        self.entry_hash.config(state="readonly", foreground="#888888", justify="center")
        self.btn_save_hash.pack_forget()
        self.chk_edit.pack_forget()
        self.root.focus()
        if run_check: self.run_validity_check_thread()

    def switch_to_readonly(self):
        self.current_state = "READONLY"
        real_hash = self.reload_hash_from_file()
        self.hash_display_var.set(real_hash)
        self.entry_hash.config(state="readonly", foreground="black", justify="left")
        self.btn_save_hash.pack_forget()
        self.chk_edit.pack(side=tk.RIGHT)

    def switch_to_editing(self):
        self.current_state = "EDITING"
        self.entry_hash.config(state="normal", foreground="black", justify="left")
        self.entry_hash.focus()
        self.btn_save_hash.pack(side=tk.RIGHT, padx=(5, 0))

    def on_entry_click(self, event):
        if self.current_state == "HIDDEN": self.switch_to_readonly()

    def on_focus_out(self, event):
        if self.current_state == "EDITING": return
        if self.current_state == "READONLY": self.root.after(100, self._check_focus_and_hide)

    def _check_focus_and_hide(self):
        focused = self.root.focus_get()
        if focused == self.chk_edit: return
        if self.current_state == "READONLY": self.switch_to_hidden(run_check=False)

    def on_edit_check_toggle(self):
        if self.is_editing_var.get(): self.switch_to_editing()
        else: self.switch_to_readonly()

    def action_save_hash(self):
        new_hash = self.hash_display_var.get().strip()
        if not new_hash:
            messagebox.showwarning("提示", "Userhash 不能为空")
            return
        self.save_config_to_file(new_hash)
        self.log("Userhash 已保存")
        self.switch_to_hidden(run_check=True)

    def run_validity_check_thread(self):
        t = threading.Thread(target=self._check_logic)
        t.daemon = True
        t.start()

    def _check_logic(self):
        self.root.after(0, lambda: self.update_status_ui("检查中...", "orange"))
        real_hash = self.reload_hash_from_file()
        if not real_hash:
            self.root.after(0, lambda: self.update_status_ui("无Hash", "gray"))
            return
        
        self.session.cookies.set('userhash', real_hash)
        try:
            res = self.session.get(CHECK_URL, timeout=8)
            res.encoding = 'utf-8'
            if AUTH_FAILURE_TEXT in res.text:
                self.root.after(0, lambda: self.update_status_ui("失效", "red"))
            else:
                self.root.after(0, lambda: self.update_status_ui("有效", "green"))
        except:
            self.root.after(0, lambda: self.update_status_ui("网络错误", "red"))

    def update_status_ui(self, text, color):
        self.hash_status_var.set(text)
        self.lbl_status.config(foreground=color)

    def toggle_start_stop(self):
        if not self.is_running:
            self.is_running = True
            self.stop_event.clear()
            self.pause_event.clear()
            self.btn_start.config(text="停止")
            self.btn_pause.config(state="normal", text="暂停")
            threading.Thread(target=self._single_backup_thread, daemon=True).start()
        else:
            if messagebox.askyesno("停止", "确定要停止任务吗？"):
                self.stop_event.set()
                if self.pause_event.is_set(): self.pause_event.clear()

    def _single_backup_thread(self):
        tid = self.thread_id_var.get().strip()
        userhash = self.reload_hash_from_file()
        base_path = self.save_path_var.get().strip()
        
        if not tid:
            self.log("错误: 请输入串号")
            self._reset_ui()
            return

        is_cookie_suspicious = False
        if not userhash: is_cookie_suspicious = True
        else:
            try:
                self.session.cookies.set('userhash', userhash)
                check_res = self.session.get(CHECK_URL, timeout=5)
                check_res.encoding = 'utf-8'
                if AUTH_FAILURE_TEXT in check_res.text: is_cookie_suspicious = True
            except: is_cookie_suspicious = True

        if is_cookie_suspicious:
            if not messagebox.askyesno("饼干无效", "部分板块内容需要有效饼干，要继续尝试保存吗？"):
                self.log("用户取消备份")
                self._reset_ui()
                return 

        self._perform_backup_task(tid, userhash, base_path, is_batch=False)
        self._reset_ui()

    def _reset_ui(self):
        self.is_running = False
        self.btn_start.config(text="开始备份", state="normal")
        self.btn_pause.config(state="disabled", text="暂停")

    def toggle_pause(self):
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.btn_pause.config(text="暂停")
            self.log("继续任务...")
        else:
            self.pause_event.set()
            self.btn_pause.config(text="继续")
            self.log("已暂停...")

    def log(self, msg):
        self.root.after(0, lambda: self._log_ui(msg))

    def _log_ui(self, msg):
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")

    def download_asset(self, url, assets_dir):
        if not url: return url
        url = url.replace('&amp;', '&')
        if url.startswith("//"): full_url = "https:" + url
        elif url.startswith("/"): full_url = "https://www.nmbxd1.com" + url
        elif not url.startswith("http"): return url
        else: full_url = url
        
        filename = os.path.basename(urlparse(full_url).path)
        if not filename or "." not in filename: filename = f"asset_{abs(hash(full_url))}.bin"
        
        # 净化文件名
        filename = self.sanitize_filename(filename)
        
        local_path = os.path.join(assets_dir, filename)
        if not os.path.exists(local_path):
            try:
                res = self.session.get(full_url, timeout=5)
                if res.status_code == 200:
                    with open(local_path, "wb") as f: f.write(res.content)
            except: pass
        return f"assets/{filename}"

    def choose_directory(self):
        p = filedialog.askdirectory()
        if p: self.save_path_var.set(p)

if __name__ == "__main__":
    root = tk.Tk()
    app = ForumBackupApp(root)
    root.mainloop()