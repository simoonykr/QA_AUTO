import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from adb_client import AdbClient, AdbError
from evidence_collector import EvidenceCollector, IssueDraft
from jira_client import JiraClient, JiraError


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class QaIssueCollectorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("QA 이슈 수집기 v0.5")
        self.root.geometry("1180x920")
        self.root.minsize(1040, 820)

        self.adb = AdbClient(PROJECT_ROOT)
        self.jira = JiraClient(PROJECT_ROOT)
        self.collector = EvidenceCollector(PROJECT_ROOT, self.adb)
        self.ui_queue = queue.Queue()

        self.package_by_display_name = {}
        self.project_by_display_name = {}
        self.issue_type_by_name = {}
        self.assignee_by_display_name = {}
        self.component_by_name = {}
        self.create_fields = []

        self.selected_device = tk.StringVar()
        self.selected_package_display = tk.StringVar()
        self.pre_log_seconds = tk.StringVar(value="30")
        self.post_log_seconds = tk.StringVar(value="10")
        self.video_seconds = tk.StringVar(value="10")
        self.record_video = tk.BooleanVar(value=False)
        self.adb_path = tk.StringVar(value=self.adb.adb_path)

        self.jira_url = tk.StringVar(value=self.jira.base_url)
        self.jira_email = tk.StringVar(value=self.jira.email)
        self.jira_token = tk.StringVar(value=self.jira.api_token)
        self.selected_project = tk.StringVar()
        self.selected_issue_type = tk.StringVar()
        self.selected_assignee = tk.StringVar()
        self.priority = tk.StringVar(value="Major")
        self.reproducibility = tk.StringVar(value="Always")
        self.test_environment = tk.StringVar(value="Stage")
        self.selected_component = tk.StringVar()
        self.labels = tk.StringVar(value="android, qa-auto")

        self.configure_styles()
        self.build_ui()
        self.root.after(100, self.process_ui_queue)

    def configure_styles(self):
        self.root.configure(bg="#f3f6fb")
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10))
        style.configure("TFrame", background="#f3f6fb")
        style.configure("Card.TFrame", background="#ffffff")
        style.configure("Header.TFrame", background="#1f4e79")
        style.configure("HeaderTitle.TLabel", background="#1f4e79", foreground="#ffffff", font=("Segoe UI Semibold", 18))
        style.configure("HeaderSub.TLabel", background="#1f4e79", foreground="#dceafe", font=("Segoe UI", 10))
        style.configure("TLabel", background="#ffffff", foreground="#1f2937")
        style.configure("Muted.TLabel", background="#ffffff", foreground="#6b7280")
        style.configure("TLabelframe", background="#ffffff", bordercolor="#d8dee9", relief="solid")
        style.configure("TLabelframe.Label", background="#ffffff", foreground="#334155", font=("Segoe UI Semibold", 10))
        style.configure("TNotebook", background="#f3f6fb", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(16, 9), font=("Segoe UI Semibold", 10))
        style.map("TNotebook.Tab", background=[("selected", "#ffffff")], foreground=[("selected", "#1f4e79")])
        style.configure("TButton", padding=(12, 7), font=("Segoe UI Semibold", 10))
        style.configure("Accent.TButton", background="#2563eb", foreground="#ffffff", bordercolor="#2563eb")
        style.map("Accent.TButton", background=[("active", "#1d4ed8"), ("disabled", "#9ca3af")])
        style.configure("Secondary.TButton", background="#e8eef8", foreground="#1f4e79", bordercolor="#c8d5e8")
        style.map("Secondary.TButton", background=[("active", "#d9e5f5")])
        style.configure("TEntry", padding=6)
        style.configure("TCombobox", padding=5)

    def build_ui(self):
        header = ttk.Frame(self.root, style="Header.TFrame", padding=(18, 16))
        header.pack(fill="x")
        ttk.Label(header, text="QA 이슈 수집기", style="HeaderTitle.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Android 로그, 스크린샷, 영상을 수집하고 Jira 이슈에 자동 첨부합니다.",
            style="HeaderSub.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=14, pady=14)

        evidence_tab = ttk.Frame(notebook, padding=12)
        jira_tab = ttk.Frame(notebook, padding=12)
        notebook.add(evidence_tab, text="증거 수집")
        notebook.add(jira_tab, text="Jira 설정")

        evidence_tab.columnconfigure(0, weight=1)
        evidence_tab.rowconfigure(2, weight=1)
        self.build_adb_frame(evidence_tab)
        self.build_target_frame(evidence_tab)
        self.build_issue_frame(evidence_tab)
        self.build_action_frame(evidence_tab)
        self.build_status_frame(evidence_tab)

        jira_tab.columnconfigure(0, weight=1)
        jira_tab.rowconfigure(2, weight=3)
        jira_tab.rowconfigure(3, weight=1)
        self.build_jira_frame(jira_tab)

    def build_adb_frame(self, parent):
        frame = self.card(parent, "ADB 설정")
        frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="ADB 경로").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        ttk.Entry(frame, textvariable=self.adb_path).grid(row=0, column=1, padx=10, pady=8, sticky="ew")
        ttk.Button(frame, text="찾기", command=self.choose_adb_path, style="Secondary.TButton").grid(row=0, column=2, padx=6, pady=8)
        ttk.Button(frame, text="저장", command=self.save_adb_path, style="Secondary.TButton").grid(row=0, column=3, padx=(0, 10), pady=8)

    def build_target_frame(self, parent):
        frame = self.card(parent, "수집 대상")
        frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="디바이스").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.device_combo = ttk.Combobox(frame, textvariable=self.selected_device, state="readonly")
        self.device_combo.grid(row=0, column=1, padx=10, pady=8, sticky="ew")
        ttk.Button(frame, text="디바이스 검색", command=self.load_devices, style="Secondary.TButton").grid(row=0, column=2, padx=10, pady=8)

        ttk.Label(frame, text="앱").grid(row=1, column=0, padx=10, pady=8, sticky="w")
        self.package_combo = ttk.Combobox(frame, textvariable=self.selected_package_display)
        self.package_combo.grid(row=1, column=1, padx=10, pady=8, sticky="ew")
        self.all_apps_button = ttk.Button(frame, text="전체 앱", command=self.load_packages, style="Secondary.TButton")
        self.all_apps_button.grid(row=1, column=2, padx=6, pady=8)
        self.running_apps_button = ttk.Button(frame, text="실행 중인 앱", command=self.load_running_apps, style="Secondary.TButton")
        self.running_apps_button.grid(row=1, column=3, padx=(0, 10), pady=8)

    def build_issue_frame(self, parent):
        frame = self.card(parent, "이슈 정보")
        frame.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(2, weight=1)
        frame.rowconfigure(3, weight=1)
        frame.rowconfigure(4, weight=1)

        self.summary_entry = self.add_entry(frame, "요약", 0)

        ttk.Label(frame, text="이슈 속성").grid(row=1, column=0, padx=10, pady=8, sticky="w")
        issue_meta_frame = ttk.Frame(frame, style="Card.TFrame")
        issue_meta_frame.grid(row=1, column=1, padx=10, pady=8, sticky="ew")
        for column in (1, 3, 5):
            issue_meta_frame.columnconfigure(column, weight=1)
        self.add_inline_combo(issue_meta_frame, "우선순위", self.priority, ["Blocker", "Critical", "Major", "Minor", "Trivial"], 0)
        self.add_inline_combo(issue_meta_frame, "테스트 환경", self.test_environment, ["Beta", "Alpha", "Stage", "Live"], 2)
        self.add_inline_combo(issue_meta_frame, "재현성", self.reproducibility, ["Always", "Sometimes", "Random", "Unable to Reproduce"], 4)
        self.add_inline_combo(issue_meta_frame, "컴포넌트", self.selected_component, [], 0, row=1)
        self.component_combo = issue_meta_frame.grid_slaves(row=1, column=1)[0]
        ttk.Button(issue_meta_frame, text="불러오기", command=self.load_jira_components, style="Secondary.TButton").grid(row=1, column=2, padx=(0, 14), pady=(8, 2), sticky="w")
        self.add_inline_combo(issue_meta_frame, "레이블", self.labels, [], 3, row=1)
        self.label_combo = issue_meta_frame.grid_slaves(row=1, column=4)[0]
        ttk.Button(issue_meta_frame, text="불러오기", command=self.load_jira_labels, style="Secondary.TButton").grid(row=1, column=5, padx=(0, 14), pady=(8, 2), sticky="w")

        self.steps_text = self.add_text(frame, "재현 절차", 2)
        self.actual_text = self.add_text(frame, "실제 결과", 3)
        self.expected_text = self.add_text(frame, "기대 결과", 4)

        option_frame = ttk.Frame(frame, style="Card.TFrame")
        option_frame.grid(row=5, column=1, padx=10, pady=8, sticky="w")
        ttk.Label(frame, text="증거 옵션").grid(row=5, column=0, padx=10, pady=8, sticky="w")
        ttk.Label(option_frame, text="이전 로그(초)").pack(side="left")
        ttk.Entry(option_frame, textvariable=self.pre_log_seconds, width=8).pack(side="left", padx=(6, 14))
        ttk.Label(option_frame, text="이후 로그(초)").pack(side="left")
        ttk.Entry(option_frame, textvariable=self.post_log_seconds, width=8).pack(side="left", padx=(6, 14))
        ttk.Checkbutton(option_frame, text="영상 녹화", variable=self.record_video).pack(side="left")
        ttk.Entry(option_frame, textvariable=self.video_seconds, width=8).pack(side="left", padx=(6, 4))
        ttk.Label(option_frame, text="초").pack(side="left")

    def build_action_frame(self, parent):
        frame = ttk.Frame(parent)
        frame.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        self.collect_button = ttk.Button(frame, text="증거 수집", command=self.start_collect, style="Secondary.TButton")
        self.collect_button.pack(side="right")
        self.collect_and_jira_button = ttk.Button(
            frame,
            text="증거 수집 후 Jira 등록",
            command=self.start_collect_and_create_jira,
            style="Accent.TButton",
        )
        self.collect_and_jira_button.pack(side="right", padx=(0, 8))

    def build_status_frame(self, parent):
        frame = self.card(parent, "작업 로그")
        frame.grid(row=4, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        self.status_text = tk.Text(frame, height=8, wrap="word", bg="#0f172a", fg="#dbeafe", insertbackground="#ffffff", relief="flat")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.status_text.yview)
        self.status_text.configure(yscrollcommand=scrollbar.set)
        self.status_text.grid(row=0, column=0, padx=(10, 0), pady=10, sticky="nsew")
        scrollbar.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="ns")

    def build_jira_frame(self, parent):
        frame = self.card(parent, "Jira 연결")
        frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="Jira URL").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        ttk.Entry(frame, textvariable=self.jira_url).grid(row=0, column=1, padx=10, pady=8, sticky="ew")
        ttk.Label(frame, text="이메일 / 계정").grid(row=1, column=0, padx=10, pady=8, sticky="w")
        ttk.Entry(frame, textvariable=self.jira_email).grid(row=1, column=1, padx=10, pady=8, sticky="ew")
        ttk.Label(frame, text="API Token").grid(row=2, column=0, padx=10, pady=8, sticky="w")
        ttk.Entry(frame, textvariable=self.jira_token, show="*").grid(row=2, column=1, padx=10, pady=8, sticky="ew")
        button_frame = ttk.Frame(frame, style="Card.TFrame")
        button_frame.grid(row=3, column=1, padx=10, pady=8, sticky="w")
        ttk.Button(button_frame, text="저장", command=self.save_jira_settings, style="Secondary.TButton").pack(side="left", padx=(0, 6))
        ttk.Button(button_frame, text="연결 테스트", command=self.test_jira_connection, style="Secondary.TButton").pack(side="left", padx=(0, 6))
        ttk.Button(button_frame, text="프로젝트 불러오기", command=self.load_jira_projects, style="Secondary.TButton").pack(side="left")

        select_frame = self.card(parent, "프로젝트 설정")
        select_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        select_frame.columnconfigure(1, weight=1)
        ttk.Label(select_frame, text="프로젝트").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.project_combo = ttk.Combobox(select_frame, textvariable=self.selected_project, state="readonly")
        self.project_combo.grid(row=0, column=1, padx=10, pady=8, sticky="ew")
        ttk.Button(select_frame, text="이슈 타입 불러오기", command=self.load_jira_issue_types, style="Secondary.TButton").grid(row=0, column=2, padx=10, pady=8)

        ttk.Label(select_frame, text="이슈 타입").grid(row=1, column=0, padx=10, pady=8, sticky="w")
        self.issue_type_combo = ttk.Combobox(select_frame, textvariable=self.selected_issue_type, state="readonly")
        self.issue_type_combo.grid(row=1, column=1, padx=10, pady=8, sticky="ew")
        ttk.Button(select_frame, text="필드 정보 불러오기", command=self.load_jira_fields, style="Secondary.TButton").grid(row=1, column=2, padx=10, pady=8)

        ttk.Label(select_frame, text="담당자").grid(row=2, column=0, padx=10, pady=8, sticky="w")
        self.assignee_combo = ttk.Combobox(select_frame, textvariable=self.selected_assignee)
        self.assignee_combo.grid(row=2, column=1, padx=10, pady=8, sticky="ew")
        ttk.Button(select_frame, text="담당자 불러오기", command=self.load_jira_assignees, style="Secondary.TButton").grid(row=2, column=2, padx=10, pady=8)

        self.build_field_frame(parent)
        self.build_jira_status_frame(parent)

    def build_field_frame(self, parent):
        field_frame = self.card(parent, "생성 필드")
        field_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        field_frame.columnconfigure(0, weight=1)
        field_frame.rowconfigure(0, weight=1)
        columns = ("required", "name", "key", "type", "allowed")
        self.field_tree = ttk.Treeview(field_frame, columns=columns, show="headings", height=16)
        headings = {"required": "필수", "name": "필드명", "key": "API 키", "type": "타입", "allowed": "허용값"}
        for key, text in headings.items():
            self.field_tree.heading(key, text=text)
        self.field_tree.column("required", width=70, anchor="center", stretch=False)
        self.field_tree.column("name", width=220, stretch=True)
        self.field_tree.column("key", width=150, stretch=False)
        self.field_tree.column("type", width=150, stretch=False)
        self.field_tree.column("allowed", width=360, stretch=True)
        tree_scrollbar = ttk.Scrollbar(field_frame, orient="vertical", command=self.field_tree.yview)
        self.field_tree.configure(yscrollcommand=tree_scrollbar.set)
        self.field_tree.grid(row=0, column=0, padx=(10, 0), pady=(10, 6), sticky="nsew")
        tree_scrollbar.grid(row=0, column=1, padx=(0, 10), pady=(10, 6), sticky="ns")
        self.required_fields_text = tk.Text(field_frame, height=7, wrap="word", bg="#f8fafc", relief="flat")
        self.required_fields_text.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="ew")

    def build_jira_status_frame(self, parent):
        frame = self.card(parent, "Jira 작업 로그")
        frame.grid(row=3, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        self.jira_status_text = tk.Text(frame, height=8, wrap="word", bg="#0f172a", fg="#dbeafe", insertbackground="#ffffff", relief="flat")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.jira_status_text.yview)
        self.jira_status_text.configure(yscrollcommand=scrollbar.set)
        self.jira_status_text.grid(row=0, column=0, padx=(10, 0), pady=10, sticky="nsew")
        scrollbar.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="ns")

    def card(self, parent, title):
        return ttk.LabelFrame(parent, text=title, padding=(10, 8))

    def add_entry(self, parent, label, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, padx=10, pady=8, sticky="nw")
        entry = ttk.Entry(parent)
        entry.grid(row=row, column=1, padx=10, pady=8, sticky="ew")
        return entry

    def add_text(self, parent, label, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, padx=10, pady=8, sticky="nw")
        text = tk.Text(parent, height=5, wrap="word", bg="#ffffff", relief="solid", borderwidth=1)
        text.grid(row=row, column=1, padx=10, pady=8, sticky="nsew")
        return text

    def add_combo(self, parent, label, variable, values, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, padx=10, pady=8, sticky="w")
        ttk.Combobox(parent, textvariable=variable, values=values, state="readonly").grid(row=row, column=1, padx=10, pady=8, sticky="ew")

    def add_inline_combo(self, parent, label, variable, values, column, row=0):
        state = "readonly" if values else "normal"
        vertical_padding = 2 if row == 0 else 8
        ttk.Label(parent, text=label).grid(row=row, column=column, padx=(0, 6), pady=(vertical_padding, 2), sticky="w")
        ttk.Combobox(parent, textvariable=variable, values=values, state=state, width=18).grid(
            row=row,
            column=column + 1,
            padx=(0, 14),
            pady=(vertical_padding, 2),
            sticky="ew",
        )

    def choose_adb_path(self):
        path = filedialog.askopenfilename(title="Select adb.exe", filetypes=[("ADB executable", "adb.exe"), ("EXE files", "*.exe"), ("All files", "*.*")])
        if path:
            self.adb_path.set(path)

    def save_adb_path(self):
        path = self.adb_path.get().strip()
        if not path:
            messagebox.showwarning("ADB 경로 필요", "ADB 경로를 입력해주세요.")
            return
        self.adb.save_adb_path(path)
        self.log_status("ADB 경로를 저장했습니다.")

    def load_devices(self):
        try:
            devices = self.adb.list_devices()
        except AdbError as exc:
            messagebox.showerror("ADB 오류", str(exc))
            return
        self.device_combo["values"] = devices
        self.selected_device.set(devices[0] if devices else "")
        self.log_status(f"디바이스 {len(devices)}개를 찾았습니다." if devices else "연결된 디바이스가 없습니다.")

    def load_packages(self):
        device_id = self.require_device()
        if not device_id:
            return
        self.log_status("앱 이름을 불러오는 중입니다. 앱이 많으면 시간이 조금 걸릴 수 있습니다.")
        self.set_package_buttons_state("disabled")
        threading.Thread(target=self.load_apps_worker, args=(device_id, False), daemon=True).start()

    def load_running_apps(self):
        device_id = self.require_device()
        if not device_id:
            return
        self.log_status("실행 중인 앱 이름을 불러오는 중입니다.")
        self.set_package_buttons_state("disabled")
        threading.Thread(target=self.load_apps_worker, args=(device_id, True), daemon=True).start()

    def load_apps_worker(self, device_id, running_only):
        try:
            apps = self.adb.list_running_apps(device_id) if running_only else self.adb.list_apps(device_id)
        except AdbError as exc:
            self.ui_queue.put(("error", str(exc)))
            self.ui_queue.put(("packages_loaded", []))
            return
        self.ui_queue.put(("packages_loaded", apps))

    def apply_package_list(self, apps):
        self.package_by_display_name = {app.display_name: app.package for app in apps}
        display_names = list(self.package_by_display_name)
        self.package_combo["values"] = display_names
        self.selected_package_display.set(display_names[0] if display_names else "")
        self.log_status(f"앱 {len(display_names)}개를 불러왔습니다.")

    def set_package_buttons_state(self, state):
        self.all_apps_button.configure(state=state)
        self.running_apps_button.configure(state=state)

    def save_jira_settings(self):
        base_url = self.jira_url.get().strip()
        email = self.jira_email.get().strip()
        token = self.jira_token.get().strip()
        if not base_url or not email or not token:
            messagebox.showwarning("Jira 설정 필요", "Jira URL, 계정, API Token을 모두 입력해주세요.")
            return False
        self.jira.save_settings(base_url, email, token)
        self.log_jira_status("Jira 설정을 저장했습니다.")
        return True

    def test_jira_connection(self):
        if not self.save_jira_settings():
            return
        self.log_jira_status("Jira 연결 테스트 중...")
        threading.Thread(target=self.test_jira_worker, daemon=True).start()

    def test_jira_worker(self):
        try:
            user = self.jira.get_myself()
        except JiraError as exc:
            self.ui_queue.put(("jira_error", str(exc)))
            return
        name = user.get("displayName") or user.get("name") or user.get("emailAddress") or "사용자"
        self.ui_queue.put(("jira_status", f"연결 성공: {name}"))

    def load_jira_projects(self):
        if not self.save_jira_settings():
            return
        self.log_jira_status("프로젝트 목록을 불러오는 중...")
        threading.Thread(target=self.load_jira_projects_worker, daemon=True).start()

    def load_jira_projects_worker(self):
        try:
            projects = self.jira.list_projects()
        except JiraError as exc:
            self.ui_queue.put(("jira_error", str(exc)))
            return
        self.ui_queue.put(("jira_projects_loaded", projects))

    def apply_jira_projects(self, projects):
        self.project_by_display_name = {project.display_name: project for project in projects}
        display_names = list(self.project_by_display_name)
        self.project_combo["values"] = display_names
        self.selected_project.set(display_names[0] if display_names else "")
        self.component_by_name = {}
        self.selected_component.set("")
        self.component_combo["values"] = []
        self.log_jira_status(f"프로젝트 {len(display_names)}개를 불러왔습니다.")

    def load_jira_issue_types(self):
        project = self.project_by_display_name.get(self.selected_project.get())
        if not project:
            messagebox.showwarning("프로젝트 필요", "Jira 프로젝트를 선택해주세요.")
            return
        self.log_jira_status(f"{project.display_name} 이슈 타입을 불러오는 중...")
        threading.Thread(target=self.load_jira_issue_types_worker, args=(project,), daemon=True).start()

    def load_jira_issue_types_worker(self, project):
        try:
            issue_types = self.jira.list_issue_types(project)
        except JiraError as exc:
            self.ui_queue.put(("jira_error", str(exc)))
            return
        self.ui_queue.put(("jira_issue_types_loaded", issue_types))

    def apply_jira_issue_types(self, issue_types):
        self.issue_type_by_name = {issue_type.name: issue_type for issue_type in issue_types}
        names = list(self.issue_type_by_name)
        self.issue_type_combo["values"] = names
        self.selected_issue_type.set(names[0] if names else "")
        self.log_jira_status(f"이슈 타입 {len(names)}개를 불러왔습니다: {', '.join(names)}")

    def load_jira_assignees(self):
        project = self.project_by_display_name.get(self.selected_project.get())
        if not project:
            messagebox.showwarning("프로젝트 필요", "Jira 프로젝트를 선택해주세요.")
            return
        query = self.selected_assignee.get().strip()
        self.log_jira_status(f"{project.key} 담당자 목록을 불러오는 중...")
        threading.Thread(target=self.load_jira_assignees_worker, args=(project, query), daemon=True).start()

    def load_jira_assignees_worker(self, project, query):
        try:
            users = self.jira.list_assignable_users(project, query=query)
        except JiraError as exc:
            self.ui_queue.put(("jira_error", str(exc)))
            return
        self.ui_queue.put(("jira_assignees_loaded", users))

    def apply_jira_assignees(self, users):
        self.assignee_by_display_name = {user.display_label: user for user in users}
        display_names = list(self.assignee_by_display_name)
        self.assignee_combo["values"] = display_names
        if display_names and not self.selected_assignee.get().strip():
            self.selected_assignee.set(display_names[0])
        self.log_jira_status(f"담당자 {len(display_names)}명을 불러왔습니다.")

    def load_jira_components(self):
        project = self.project_by_display_name.get(self.selected_project.get())
        if not project:
            messagebox.showwarning("프로젝트 필요", "Jira 프로젝트를 선택해주세요.")
            return
        self.log_jira_status(f"{project.key} 컴포넌트 목록을 불러오는 중...")
        threading.Thread(target=self.load_jira_components_worker, args=(project,), daemon=True).start()

    def load_jira_components_worker(self, project):
        try:
            components = self.jira.list_components(project)
        except JiraError as exc:
            self.ui_queue.put(("jira_error", str(exc)))
            return
        self.ui_queue.put(("jira_components_loaded", components))

    def apply_jira_components(self, components):
        self.component_by_name = {component.name: component for component in components}
        names = list(self.component_by_name)
        self.component_combo["values"] = names
        if names and not self.selected_component.get().strip():
            self.selected_component.set(names[0])
        self.log_jira_status(f"컴포넌트 {len(names)}개를 불러왔습니다.")

    def load_jira_labels(self):
        if not self.jira.is_configured() and not self.save_jira_settings():
            return
        self.log_jira_status("레이블 목록을 불러오는 중...")
        threading.Thread(target=self.load_jira_labels_worker, daemon=True).start()

    def load_jira_labels_worker(self):
        try:
            labels = self.jira.list_labels()
        except JiraError as exc:
            self.ui_queue.put(("jira_error", str(exc)))
            return
        self.ui_queue.put(("jira_labels_loaded", labels))

    def apply_jira_labels(self, labels):
        self.label_combo["values"] = labels
        self.log_jira_status(f"레이블 {len(labels)}개를 불러왔습니다. 여러 개는 쉼표로 입력하세요.")

    def load_jira_fields(self):
        project, issue_type = self.get_selected_jira_context()
        if project is None or issue_type is None:
            return
        self.log_jira_status(f"{project.key} / {issue_type.name} 생성 필드를 불러오는 중...")
        threading.Thread(target=self.load_jira_fields_worker, args=(project, issue_type), daemon=True).start()

    def load_jira_fields_worker(self, project, issue_type):
        try:
            fields = self.jira.list_create_fields(project, issue_type)
        except JiraError as exc:
            self.ui_queue.put(("jira_error", str(exc)))
            return
        self.ui_queue.put(("jira_fields_loaded", fields))

    def apply_jira_fields(self, fields):
        self.create_fields = fields
        self.field_tree.delete(*self.field_tree.get_children())
        self.required_fields_text.delete("1.0", tk.END)
        required_fields = []
        for field in fields:
            self.field_tree.insert("", tk.END, values=("Y" if field.required else "", field.name, field.key, field.field_type, ", ".join(field.allowed_values)))
            if field.required:
                required_fields.append(f"- {field.name} ({field.key})")
        required_summary = "\n".join(required_fields) if required_fields else "필수 필드가 없습니다."
        self.required_fields_text.insert(tk.END, f"필수 필드\n{required_summary}")
        self.log_jira_status(f"생성 필드 {len(fields)}개를 불러왔습니다. 필수 필드 {len(required_fields)}개.")

    def start_collect(self):
        draft = self.build_draft()
        if draft is None:
            return
        self.set_collect_buttons_state("disabled")
        self.log_status("증거 수집을 시작합니다.")
        threading.Thread(target=self.collect_worker, args=(draft,), daemon=True).start()

    def collect_worker(self, draft):
        try:
            issue_dir, metadata = self.collector.collect(draft, progress=self.enqueue_status)
        except Exception as exc:
            self.ui_queue.put(("error", str(exc)))
            return
        self.ui_queue.put(("done", str(issue_dir), metadata.get("log_before_count", 0), metadata.get("log_after_count", 0)))

    def start_collect_and_create_jira(self):
        draft = self.build_draft()
        project, issue_type = self.get_selected_jira_context()
        if draft is None or project is None or issue_type is None:
            return
        if not self.validate_jira_required_fields():
            return
        self.set_collect_buttons_state("disabled")
        self.log_status("증거 수집 후 Jira 등록을 시작합니다.")
        self.log_jira_status("증거 수집 후 Jira 이슈 생성 및 첨부 업로드를 시작합니다.")
        threading.Thread(target=self.collect_and_create_jira_worker, args=(project, issue_type, draft), daemon=True).start()

    def collect_and_create_jira_worker(self, project, issue_type, draft):
        try:
            issue_dir, metadata = self.collector.collect(draft, progress=self.enqueue_status)
            if not self.create_fields:
                self.create_fields = self.jira.list_create_fields(project, issue_type)
            device_info = metadata.get("device") or self.adb.get_device_info(draft.device_id)
            app_info = metadata.get("app") or self.adb.get_app_info(draft.device_id, draft.package_name)
            result = self.jira.create_issue(
                project=project,
                issue_type=issue_type,
                summary=draft.summary,
                description_text=self.build_jira_description(draft, app_info, metadata.get("files", {})),
                device_environment=self.build_device_environment(device_info),
                labels=self.get_labels(),
                fields=self.create_fields,
                assignee=self.get_selected_assignee(),
                priority=self.priority.get(),
                reproducibility=self.reproducibility.get(),
                test_environment=self.test_environment.get(),
                component=self.get_selected_component(),
            )
            issue_key = result.get("key", "")
            if not issue_key:
                raise JiraError("Jira 이슈는 생성됐지만 응답에서 이슈 키를 찾지 못했습니다.")
            files = self.get_attachment_files(metadata)
            self.ui_queue.put(("jira_status", f"{issue_key}에 첨부 {len(files)}개 업로드 중..."))
            uploaded = self.jira.upload_attachments(issue_key, files)
        except (JiraError, AdbError, OSError) as exc:
            self.ui_queue.put(("error", str(exc)))
            self.ui_queue.put(("jira_error", str(exc)))
            return
        issue_url = f"{self.jira.base_url}/browse/{issue_key}"
        self.ui_queue.put(("collect_jira_done", str(issue_dir), issue_key, issue_url, len(uploaded)))

    def build_draft(self):
        summary = self.summary_entry.get().strip()
        package_name = self.get_selected_package_name()
        device_id = self.selected_device.get().strip()
        if not summary:
            messagebox.showwarning("요약 필요", "이슈 요약을 입력해주세요.")
            return None
        if not device_id:
            messagebox.showwarning("디바이스 필요", "디바이스를 선택해주세요.")
            return None
        if not package_name:
            messagebox.showwarning("앱 필요", "앱을 선택하거나 패키지명을 입력해주세요.")
            return None
        try:
            pre_log_seconds = int(self.pre_log_seconds.get())
            post_log_seconds = int(self.post_log_seconds.get())
            video_seconds = int(self.video_seconds.get())
            if pre_log_seconds <= 0 or post_log_seconds <= 0 or video_seconds <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("입력 오류", "로그/영상 시간은 양의 정수로 입력해주세요.")
            return None
        return IssueDraft(
            summary=summary,
            steps=self.get_text(self.steps_text),
            actual_result=self.get_text(self.actual_text),
            expected_result=self.get_text(self.expected_text),
            severity=self.priority.get(),
            package_name=package_name,
            device_id=device_id,
            pre_log_seconds=pre_log_seconds,
            post_log_seconds=post_log_seconds,
            record_video=self.record_video.get(),
            video_seconds=video_seconds,
        )

    def build_jira_description(self, draft, app_info, files=None):
        files = files or {}
        attachment_lines = []
        for label, key in (("이전 로그", "logcat_before"), ("이후 로그", "logcat_after"), ("스크린샷", "screenshot"), ("영상", "screenrecord")):
            if files.get(key):
                attachment_lines.append(f"- {label}: {Path(files[key]).name}")
        if not attachment_lines:
            attachment_lines = ["- 증거 수집 후 첨부 예정"]
        return "\n".join(
            [
                "[재현 절차]",
                draft.steps or "-",
                "",
                "[실제 결과]",
                draft.actual_result or "-",
                "",
                "[기대 결과]",
                draft.expected_result or "-",
                "",
                "[앱 정보]",
                f"앱 이름: {app_info.get('label') or draft.package_name}",
                f"패키지: {draft.package_name}",
                f"버전: {app_info.get('version_name', '')} ({app_info.get('version_code', '')})",
                "",
                "[첨부 파일]",
                *attachment_lines,
            ]
        )

    def build_device_environment(self, device_info):
        return "\n".join(
            [
                f"제조사: {device_info.get('manufacturer', '')}",
                f"모델: {device_info.get('model', '')}",
                f"Android: {device_info.get('android_version', '')}",
                f"SDK: {device_info.get('sdk', '')}",
            ]
        )

    def get_attachment_files(self, metadata):
        files = metadata.get("files", {})
        paths = []
        for key in ("logcat_before", "logcat_after", "screenshot", "screenrecord"):
            if files.get(key):
                paths.append(files[key])
        return paths

    def get_selected_jira_context(self):
        project = self.project_by_display_name.get(self.selected_project.get())
        issue_type = self.issue_type_by_name.get(self.selected_issue_type.get())
        if not project:
            messagebox.showwarning("프로젝트 필요", "Jira 프로젝트를 선택해주세요.")
            return None, None
        if not issue_type:
            messagebox.showwarning("이슈 타입 필요", "Jira 이슈 타입을 선택해주세요.")
            return None, None
        return project, issue_type

    def validate_jira_required_fields(self):
        if self.is_field_required("assignee") and not self.get_selected_assignee():
            messagebox.showwarning("담당자 필요", "담당자 필드가 필수입니다. 담당자를 불러온 뒤 선택해주세요.")
            return False
        if self.is_field_required("components") and not self.get_selected_component():
            messagebox.showwarning("컴포넌트 필요", "컴포넌트 필드가 필수입니다. 컴포넌트를 불러온 뒤 선택해주세요.")
            return False
        if self.is_field_required("labels") and not self.get_labels():
            messagebox.showwarning("레이블 필요", "레이블 필드가 필수입니다. 레이블을 입력해주세요.")
            return False
        return True

    def get_selected_assignee(self):
        return self.assignee_by_display_name.get(self.selected_assignee.get().strip())

    def get_selected_component(self):
        return self.component_by_name.get(self.selected_component.get().strip())

    def get_labels(self):
        values = []
        for label in self.labels.get().replace("\n", ",").split(","):
            cleaned = label.strip()
            if cleaned and cleaned not in values:
                values.append(cleaned)
        return values

    def is_field_required(self, field_key):
        return any(field.key == field_key and field.required for field in self.create_fields)

    def get_selected_package_name(self):
        value = self.selected_package_display.get().strip()
        if value in self.package_by_display_name:
            return self.package_by_display_name[value]
        if value.endswith(")") and "(" in value:
            return value.rsplit("(", 1)[1][:-1].strip()
        return value

    def require_device(self):
        device_id = self.selected_device.get().strip()
        if not device_id:
            messagebox.showwarning("디바이스 필요", "먼저 디바이스를 검색하고 선택해주세요.")
            return None
        return device_id

    def get_text(self, widget):
        return widget.get("1.0", tk.END).strip()

    def enqueue_status(self, message):
        self.ui_queue.put(("status", message))

    def set_collect_buttons_state(self, state):
        self.collect_button.configure(state=state)
        self.collect_and_jira_button.configure(state=state)

    def process_ui_queue(self):
        while True:
            try:
                item = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            event = item[0]
            if event == "status":
                self.log_status(item[1])
            elif event == "error":
                self.set_collect_buttons_state("normal")
                self.set_package_buttons_state("normal")
                self.log_status(f"오류: {item[1]}")
                messagebox.showerror("오류", item[1])
            elif event == "packages_loaded":
                self.set_package_buttons_state("normal")
                self.apply_package_list(item[1])
            elif event == "done":
                self.set_collect_buttons_state("normal")
                self.log_status(f"완료: {item[1]}")
                self.log_status(f"수집된 로그 라인: 이전 {item[2]} / 이후 {item[3]}")
                messagebox.showinfo("증거 수집 완료", f"증거 수집이 완료되었습니다.\n{item[1]}")
            elif event == "jira_status":
                self.log_jira_status(item[1])
            elif event == "jira_error":
                self.log_jira_status(f"오류: {item[1]}")
                messagebox.showerror("Jira 오류", item[1])
            elif event == "jira_projects_loaded":
                self.apply_jira_projects(item[1])
            elif event == "jira_issue_types_loaded":
                self.apply_jira_issue_types(item[1])
            elif event == "jira_assignees_loaded":
                self.apply_jira_assignees(item[1])
            elif event == "jira_components_loaded":
                self.apply_jira_components(item[1])
            elif event == "jira_labels_loaded":
                self.apply_jira_labels(item[1])
            elif event == "jira_fields_loaded":
                self.apply_jira_fields(item[1])
            elif event == "collect_jira_done":
                self.set_collect_buttons_state("normal")
                issue_dir, issue_key, issue_url, upload_count = item[1], item[2], item[3], item[4]
                self.log_status(f"Jira 등록 완료: {issue_key}")
                self.log_jira_status(f"이슈 생성 및 첨부 완료: {issue_key}")
                self.log_jira_status(f"첨부 업로드 완료: {upload_count}개")
                self.log_jira_status(issue_url)
                messagebox.showinfo("Jira 등록 완료", f"{issue_key}\n첨부 {upload_count}개 업로드 완료\n{issue_dir}\n{issue_url}")
        self.root.after(100, self.process_ui_queue)

    def log_status(self, message):
        self.status_text.insert(tk.END, f"{message}\n")
        self.status_text.see(tk.END)

    def log_jira_status(self, message):
        self.jira_status_text.insert(tk.END, f"{message}\n")
        self.jira_status_text.see(tk.END)


def main():
    root = tk.Tk()
    QaIssueCollectorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
