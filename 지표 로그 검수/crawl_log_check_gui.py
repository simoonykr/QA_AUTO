# -*- coding: utf-8 -*-
"""
지표 로그 크롤링 GUI V5
- Chrome 수동 로그인/검색
- logListDiv 테이블 크롤링 (현재 페이지 / 전체 페이지, 누적 모드)
- 로그정의서(검수 엑셀) 로드 → 정의 여부 / 필드 누락 / 수치 계산 / 수치 연속성 자동 검증
- 재화 매핑(rCurrency → 정의서 재화명) 설정
- 정의서 사본의 AOS/IOS 결과 칸에 Pass/Fail 자동 기입
- 필터, 체크박스, 통계, Excel 저장
"""

import re
import subprocess
import time
import tkinter as tk
from collections import Counter
from datetime import datetime
from pathlib import Path
from tkinter import ttk, filedialog, messagebox, simpledialog
from tkinter.scrolledtext import ScrolledText

import pandas as pd
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

import log_verifier as lv


# ---------------------------
# 유틸 함수
# ---------------------------
# reason=값 / reason: 값 / "reason":"값" / 'reason'='값' 형식 모두 인식
# (앞에 영문/숫자/_가 붙은 subreason= 같은 키는 제외)
_REASON_RE = re.compile(
    r"""(?<![A-Za-z0-9_])["']?reason["']?\s*[=:]\s*(?:"([^"]*)"|'([^']*)'|([^,}\]]+))"""
)


def normalize_reason(value) -> str:
    """reason 값 비교용 정규화: 공백/따옴표 제거, 1001.0 → 1001"""
    if value is None:
        return ""
    s = str(value).strip().strip("\"'").strip()
    if s.lower() == "nan":
        return ""
    if re.fullmatch(r"-?\d+\.0+", s):
        s = s.split(".")[0]
    return s


def extract_reason_from_log(loginfo: str) -> str:
    """로그정보 문자열에서 reason 값 추출"""
    if not loginfo:
        return ""
    m = _REASON_RE.search(loginfo)
    if not m:
        return ""
    return normalize_reason(next(g for g in m.groups() if g is not None))


RESULT_FILTERS = ["전체", "문제만 (Fail/미정의/경고)", "Fail", "미정의", "경고", "Pass", "대상아님"]

# 페이지 이동 JS -------------------------------------------------------------
_JS_DT_INFO = """
const root = document.getElementById('logListDiv');
const $ = window.jQuery;
if (!root || !$ || !$.fn || !$.fn.dataTable) return null;
const t = root.querySelector('table');
if (!t || !$.fn.dataTable.isDataTable(t)) return null;
const i = $(t).DataTable().page.info();
return {page: i.page, pages: i.pages};
"""

_JS_DT_GOTO = """
const t = document.getElementById('logListDiv').querySelector('table');
window.jQuery(t).DataTable().page(arguments[0]).draw('page');
"""

_JS_SIGNATURE = """
const root = document.getElementById('logListDiv');
if (!root) return '';
const trs = root.querySelectorAll("tbody tr");
if (!trs.length) return 'EMPTY';
return trs.length + '|' + trs[0].innerText + '|' + trs[trs.length - 1].innerText;
"""

# DataTables 가 아닐 때: '다음' 버튼을 찾아서 클릭
_JS_CLICK_NEXT = """
const sel = '.paginate_button.next, li.next > a, a.next, .pagination .next, '
          + 'a[aria-label="Next"], a[aria-label="다음"], button[aria-label="Next"]';
const cands = [...document.querySelectorAll(sel)];
document.querySelectorAll('a, button').forEach(e => {
  const t = (e.textContent || '').trim();
  if (['다음', 'Next', '›', '>', '다음 페이지'].includes(t)) cands.push(e);
});
for (const c of cands) {
  // li.next 처럼 컨테이너가 잡히면 안쪽의 링크/버튼을 클릭해야 이벤트가 동작함
  const e = c.matches('a, button') ? c : (c.querySelector('a, button') || c);
  if (!e.offsetParent) continue;
  const li = e.closest('li');
  const dis = c.classList.contains('disabled') || e.classList.contains('disabled')
           || (li && li.classList.contains('disabled'))
           || e.getAttribute('aria-disabled') === 'true' || e.disabled;
  if (dis) return 'disabled';
  e.click();
  return 'clicked';
}
return 'none';
"""


# ---------------------------
# 메인 GUI
# ---------------------------
class LogCrawlerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("지표 로그 크롤링 GUI V5 (서비스QA 전용)")
        self.geometry("1500x950")

        # 상태
        self.driver = None
        self.data_rows = []         # 전체 데이터
        self.filtered_rows = []     # 필터 적용된 뷰
        self.definition = None      # 로그정의서 (lv.LogDefinition)
        self.config = lv.load_config()

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self._update_status()

    # -------------------- 종료 처리 --------------------
    def _quit_driver(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

    def on_close(self):
        self._quit_driver()
        self.destroy()

    # -------------------- UI 구성 --------------------
    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=(8, 2))
        ttk.Button(top, text="1) Start Browser", command=self.start_browser).pack(side="left", padx=4)
        ttk.Button(top, text="2) 로그정의서 로드", command=self.load_definition).pack(side="left", padx=4)
        ttk.Button(top, text="재화 매핑 설정", command=self.edit_currency_map).pack(side="left", padx=4)
        self.lbl_status = ttk.Label(top, text="", foreground="#555")
        self.lbl_status.pack(side="left", padx=12)

        top2 = ttk.Frame(self)
        top2.pack(fill="x", padx=10, pady=(2, 8))
        ttk.Button(top2, text="3) 현재 페이지 크롤링", command=self.crawl_logs).pack(side="left", padx=4)
        ttk.Button(top2, text="3) 전체 페이지 크롤링", command=self.crawl_all_pages).pack(side="left", padx=4)
        self.var_append = tk.BooleanVar(value=False)
        ttk.Checkbutton(top2, text="누적 (기존 결과에 추가)", variable=self.var_append).pack(side="left", padx=4)
        ttk.Button(top2, text="4) 정의서에 결과 기입", command=self.write_to_definition).pack(side="left", padx=(16, 4))
        ttk.Separator(top2, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(top2, text="전체 Excel 저장", command=self.save_all_to_excel).pack(side="left", padx=4)
        ttk.Button(top2, text="체크된 것만 저장", command=self.save_checked_to_excel).pack(side="left", padx=4)
        ttk.Button(top2, text="통계 보기", command=self.show_reason_stats).pack(side="left", padx=4)

        # 필터 영역
        filter_frm = ttk.LabelFrame(self, text="필터 (조건을 모두 만족하는 행만 표시)")
        filter_frm.pack(fill="x", padx=10, pady=5)
        ttk.Button(filter_frm, text="현재 필터 전체 체크", command=self.check_all_filtered).pack(side="left", padx=6)
        ttk.Button(filter_frm, text="현재 필터 전체 해제", command=self.uncheck_all_filtered).pack(side="left", padx=6)

        ttk.Label(filter_frm, text="텍스트:").pack(side="left", padx=3)
        self.ent_filter = ttk.Entry(filter_frm, width=30)
        self.ent_filter.pack(side="left", padx=3)

        ttk.Label(filter_frm, text="reason:").pack(side="left", padx=(10, 3))
        self.ent_reason_filter = ttk.Entry(filter_frm, width=20)
        self.ent_reason_filter.pack(side="left", padx=3)

        ttk.Label(filter_frm, text="검증결과:").pack(side="left", padx=(10, 3))
        self.cmb_result = ttk.Combobox(filter_frm, values=RESULT_FILTERS, state="readonly", width=22)
        self.cmb_result.current(0)
        self.cmb_result.pack(side="left", padx=3)
        self.cmb_result.bind("<<ComboboxSelected>>", lambda e: self.apply_filters())

        ttk.Button(filter_frm, text="필터 적용", command=self.apply_filters).pack(side="left", padx=6)
        ttk.Button(filter_frm, text="필터 초기화", command=self.reset_filter).pack(side="left", padx=4)
        for ent in (self.ent_filter, self.ent_reason_filter):
            ent.bind("<Return>", lambda e: self.apply_filters())

        # 테이블
        table_frm = ttk.LabelFrame(self, text="크롤링 결과 (더블클릭: 상세 / 같은 log_tx 로그 보기)")
        table_frm.pack(fill="both", expand=True, padx=10, pady=5)

        cols = ("Check", "게임명", "App ID", "로그시간", "로그타입", "태그1", "reason", "검증", "검증상세", "로그정보")
        self.tree = ttk.Treeview(table_frm, columns=cols, show="headings", height=25)
        widths = {"Check": 50, "게임명": 80, "App ID": 70, "로그시간": 140, "로그타입": 80, "태그1": 50,
                  "reason": 140, "검증": 65, "검증상세": 380, "로그정보": 600}
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=widths[c], anchor="center" if c in ("Check", "검증") else "w",
                             stretch=(c == "로그정보"))

        ysb = ttk.Scrollbar(table_frm, orient="vertical", command=self.tree.yview)
        xsb = ttk.Scrollbar(table_frm, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscroll=ysb.set, xscroll=xsb.set)
        ysb.pack(side="right", fill="y")
        xsb.pack(side="bottom", fill="x")
        self.tree.pack(fill="both", expand=True, side="left")

        self.tree.bind("<Button-1>", self.on_tree_click)
        self.tree.bind("<Double-1>", self.on_tree_double_click)

        self.tree.tag_configure("fail", background="#ffc9c9")
        self.tree.tag_configure("undef", background="#ffd8a8")
        self.tree.tag_configure("warn", background="#fff3bf")

        # 로그 출력
        log_frm = ttk.LabelFrame(self, text="로그 출력")
        log_frm.pack(fill="both", padx=10, pady=5)
        self.txt_log = ScrolledText(log_frm, height=8)
        self.txt_log.pack(fill="both", expand=True, padx=5, pady=5)

    def _update_status(self):
        d = f"정의서: {Path(self.definition.path).name} ({len(self.definition.rows)}개 정의)" \
            if self.definition else "정의서: 미로드 (수치 검증만 수행)"
        self.lbl_status.config(text=f"{d}   |   재화 매핑 {len(self.config.get('currency_map', {}))}개")

    # -------------------- 현재 필터 전체 체크 --------------------
    def check_all_filtered(self):
        for row in self.filtered_rows:
            row["checked"] = True
        self.refresh_table()
        self.log(f"✔ 필터된 {len(self.filtered_rows)}개 항목 전체 체크 완료")

    # -------------------- 현재 필터 전체 해제 --------------------
    def uncheck_all_filtered(self):
        for row in self.filtered_rows:
            row["checked"] = False
        self.refresh_table()
        self.log(f"✔ 필터된 {len(self.filtered_rows)}개 항목 전체 해제 완료")

    # -------------------- 로그 출력 --------------------
    def log(self, msg):
        self.txt_log.insert(tk.END, msg + "\n")
        self.txt_log.see(tk.END)

    # -------------------- Selenium --------------------
    def _admin_url(self):
        """설정 파일의 어드민 주소. 없으면 입력받아 저장 (주소는 코드/저장소에 두지 않음)"""
        url = self.config.get("admin_url", "").strip()
        if url:
            return url
        url = (simpledialog.askstring(
            "어드민 주소 입력",
            "로그 조회 페이지 주소를 입력하세요.\n(한 번 입력하면 설정 파일에 저장됩니다)",
            parent=self) or "").strip()
        if url:
            self.config["admin_url"] = url
            lv.save_config(self.config)
            self.log(f"✔ 어드민 주소 저장 → {lv.CONFIG_PATH.name}")
        return url

    def start_browser(self):
        try:
            self._quit_driver()  # 이미 띄운 브라우저가 있으면 정리 후 새로 실행
            self.log("▶ Chrome 실행 중…")
            options = webdriver.ChromeOptions()
            options.add_argument("--start-maximized")

            url = self._admin_url()
            if not url:
                return

            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            self.driver.get(url)

            self.log(f"▶ URL 접속: {url}")
            self.log("▶ 로그인 및 검색조건은 수동으로 진행해주세요.")
        except Exception as e:
            messagebox.showerror("오류", str(e))

    # -------------------- 로그정의서 로드 --------------------
    def load_definition(self):
        path = filedialog.askopenfilename(
            title="로그정의서(검수 엑셀) 선택",
            filetypes=[("Excel files", "*.xlsx")]
        )
        if not path:
            return
        try:
            self.definition = lv.LogDefinition(path)
        except PermissionError:
            messagebox.showerror("오류", "파일이 Excel에서 열려 있어 읽을 수 없습니다. 닫고 다시 시도해주세요.")
            return
        except Exception as e:
            messagebox.showerror("오류", f"정의서 로드 실패:\n{e}")
            return

        by_sheet = Counter(d.sheet for d in self.definition.rows)
        self.log(f"✔ 로그정의서 로드: {Path(path).name}")
        for s, n in by_sheet.items():
            self.log(f"   - {s}: {n}개 정의")
        self.log(f"   - 정의서 재화명: {', '.join(self.definition.currencies())}")
        self._update_status()
        self.run_verification()

    # -------------------- 재화 매핑 설정 --------------------
    def edit_currency_map(self):
        cmap = self.config.get("currency_map", {})
        seen = sorted({r["fields"].get("rCurrency", "") for r in self.data_rows
                       if r["로그타입"] in ("cashitem", "resource")} - {""})
        unmapped = [c for c in seen if c not in cmap]

        win = tk.Toplevel(self)
        win.title("재화 매핑 설정 (rCurrency → 정의서 재화명)")
        win.geometry("560x520")

        info = ("한 줄에 하나씩  '로그의 rCurrency = 정의서의 재화명'  형식으로 입력하세요.\n"
                "값이 비어 있는 줄은 저장되지 않습니다. # 으로 시작하는 줄은 주석입니다.")
        ttk.Label(win, text=info, justify="left").pack(anchor="w", padx=10, pady=(10, 2))
        if self.definition:
            ttk.Label(win, text="정의서 재화명: " + ", ".join(self.definition.currencies()),
                      foreground="#1c7ed6").pack(anchor="w", padx=10)

        txt = ScrolledText(win, height=20)
        txt.pack(fill="both", expand=True, padx=10, pady=6)
        lines = [f"{k} = {v}" for k, v in cmap.items()]
        if unmapped:
            lines += ["", "# 크롤링된 로그 중 매핑이 없는 재화 (필요하면 값을 채워주세요)"]
            lines += [f"{c} = " for c in unmapped]
        txt.insert(tk.END, "\n".join(lines))

        def save():
            new_map = {}
            for line in txt.get("1.0", tk.END).splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = (s.strip() for s in line.split("=", 1))
                if k and v:
                    new_map[k] = v
            self.config["currency_map"] = new_map
            try:
                lv.save_config(self.config)
            except Exception as e:
                messagebox.showerror("저장 실패", str(e), parent=win)
                return
            self.log(f"✔ 재화 매핑 저장 ({len(new_map)}개) → {lv.CONFIG_PATH.name}")
            self._update_status()
            self.run_verification()
            win.destroy()

        def open_config_file():
            if not lv.CONFIG_PATH.exists():
                lv.save_config(self.config)
            subprocess.Popen(["notepad.exe", str(lv.CONFIG_PATH)])

        btns = ttk.Frame(win)
        btns.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(btns, text="저장", command=save).pack(side="right", padx=4)
        ttk.Button(btns, text="취소", command=win.destroy).pack(side="right", padx=4)
        ttk.Button(btns, text="설정 파일 직접 열기 (고급)", command=open_config_file).pack(side="left")

    # -------------------- 로그 크롤링 --------------------
    def _parse_current_page(self):
        """현재 화면의 logListDiv 테이블 → raw row dict 리스트"""
        html = self.driver.find_element(By.ID, "logListDiv").get_attribute("innerHTML")
        soup = BeautifulSoup(html, "html.parser")

        raws = []
        for tr in soup.select("tbody tr[role='row']"):
            tds = tr.find_all("td")
            if len(tds) < 6:
                continue
            raws.append({
                "게임명": tds[0].get_text(strip=True),
                "App ID": tds[1].get_text(strip=True),
                "로그시간": tds[2].get_text(strip=True),
                "로그타입": tds[3].get_text(strip=True),
                "태그1": tds[4].get_text(strip=True),
                "로그정보": tds[5].get_text(strip=True),
            })
        return raws

    @staticmethod
    def _row_key(r):
        return (r["게임명"], r["App ID"], r["로그시간"], r["로그타입"], r["태그1"], r["로그정보"])

    def _ingest(self, raws, append):
        """크롤링 결과 반영 (누적이면 중복 제외 후 추가) → 추가된 건수"""
        base = list(self.data_rows) if append else []
        keys = {self._row_key(r) for r in base}
        next_id = max((r["id"] for r in base), default=-1) + 1

        added = 0
        for raw in raws:
            k = self._row_key(raw)
            if k in keys:
                continue
            keys.add(k)
            fields = lv.parse_loginfo(raw["로그정보"])
            reason = normalize_reason(fields.get("reason")) or extract_reason_from_log(raw["로그정보"])
            base.append({**raw, "id": next_id, "checked": False, "reason": reason, "fields": fields})
            next_id += 1
            added += 1

        self.data_rows = base
        self.run_verification()
        return added

    def crawl_logs(self):
        if not self.driver:
            messagebox.showwarning("알림", "Start Browser 먼저 실행!")
            return

        self.log("=== 현재 페이지 크롤링 ===")
        try:
            raws = self._parse_current_page()
            added = self._ingest(raws, self.var_append.get())
            self.log(f"✔ {len(raws)}개 row 크롤링 → {added}개 추가 (전체 {len(self.data_rows)}개)")
        except Exception as e:
            messagebox.showerror("오류", str(e))

    # -------------------- 전체 페이지 크롤링 --------------------
    def _signature(self):
        try:
            return self.driver.execute_script(_JS_SIGNATURE)
        except Exception:
            return None

    def _wait_page_change(self, old_sig, timeout=15.0):
        """테이블 내용이 바뀔 때까지 대기 (GUI 멈춤 방지를 위해 update 호출)"""
        end = time.time() + timeout
        while time.time() < end:
            self.update()
            sig = self._signature()
            if sig and sig != old_sig:
                time.sleep(0.3)  # 렌더링 마무리 대기
                return True
            time.sleep(0.3)
        return False

    def crawl_all_pages(self):
        if not self.driver:
            messagebox.showwarning("알림", "Start Browser 먼저 실행!")
            return

        self.log("=== 전체 페이지 크롤링 시작 ===")
        all_raws, pages = [], 0
        try:
            dt = None
            try:
                dt = self.driver.execute_script(_JS_DT_INFO)
            except Exception:
                pass

            if dt and dt.get("pages", 0) > 0:
                # DataTables: API로 페이지 이동
                total, start_page = dt["pages"], dt["page"]
                self.log(f"▶ DataTables 페이지 {total}개 감지")
                for p in range(total):
                    if p != self._current_dt_page():
                        sig = self._signature()
                        self.driver.execute_script(_JS_DT_GOTO, p)
                        self._wait_page_change(sig)
                    all_raws += self._parse_current_page()
                    pages += 1
                    self.log(f"   - {p + 1}/{total} 페이지 ({len(all_raws)}건)")
                    self.update()
                if start_page != self._current_dt_page():
                    self.driver.execute_script(_JS_DT_GOTO, start_page)
            else:
                # 일반 페이지네이션: '다음' 버튼 클릭 반복
                for _ in range(1000):
                    all_raws += self._parse_current_page()
                    pages += 1
                    self.log(f"   - {pages} 페이지 ({len(all_raws)}건)")
                    self.update()

                    sig = self._signature()
                    res = self.driver.execute_script(_JS_CLICK_NEXT)
                    if res == "none":
                        if pages == 1:
                            self.log("⚠ '다음 페이지' 버튼을 찾지 못해 현재 페이지만 수집했습니다. "
                                     "페이지를 직접 넘기면서 '누적' 체크 후 '현재 페이지 크롤링'을 사용하세요.")
                        break
                    if res == "disabled":
                        break
                    if not self._wait_page_change(sig):
                        self.log("⚠ 페이지가 바뀌지 않아 수집을 종료합니다.")
                        break

            added = self._ingest(all_raws, self.var_append.get())
            self.log(f"✔ {pages}개 페이지, {len(all_raws)}건 수집 → {added}건 추가 (전체 {len(self.data_rows)}건)")
        except Exception as e:
            if all_raws:
                added = self._ingest(all_raws, self.var_append.get())
                self.log(f"⚠ 수집 중 오류로 중단: {e} → 그때까지 {added}건 반영")
            messagebox.showerror("오류", str(e))

    def _current_dt_page(self):
        try:
            return (self.driver.execute_script(_JS_DT_INFO) or {}).get("page", 0)
        except Exception:
            return 0

    # -------------------- 검증 --------------------
    def run_verification(self):
        if not self.data_rows:
            self.apply_filters()
            return
        lv.verify_rows(self.data_rows, self.definition, self.config)
        cnt = Counter(r["result"] for r in self.data_rows)
        self.log("▶ 검증 결과: " + ", ".join(f"{k} {v}건" for k, v in cnt.most_common()))
        if not self.definition:
            self.log("   (로그정의서 미로드: 수치 계산/연속성만 검증했습니다)")
        self.apply_filters()

    # -------------------- 테이블 갱신 --------------------
    def _row_tags(self, row):
        res = row.get("result")
        if res == lv.RESULT_FAIL:
            return ("fail",)
        if res == lv.RESULT_UNDEF:
            return ("undef",)
        if res == lv.RESULT_WARN:
            return ("warn",)
        return ()

    def _row_values(self, row):
        return (
            "☑" if row["checked"] else "□",
            row["게임명"], row["App ID"], row["로그시간"], row["로그타입"], row["태그1"],
            row["reason"], row.get("result", ""), row.get("detail", ""), row["로그정보"],
        )

    def refresh_table(self):
        self.tree.delete(*self.tree.get_children())
        for row in self.filtered_rows:
            self.tree.insert("", "end", iid=str(row["id"]), values=self._row_values(row),
                             tags=self._row_tags(row))

    # -------------------- 체크박스 토글 --------------------
    def on_tree_click(self, event):
        col = self.tree.identify_column(event.x)
        row_id = self.tree.identify_row(event.y)

        if col != "#1" or not row_id:
            return

        rid = int(row_id)
        row = next(r for r in self.data_rows if r["id"] == rid)
        row["checked"] = not row["checked"]
        self.tree.set(row_id, "Check", "☑" if row["checked"] else "□")  # 해당 행만 갱신

        return "break"

    # -------------------- 상세 팝업 --------------------
    def on_tree_double_click(self, event):
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return

        rid = int(row_id)
        row = next(r for r in self.data_rows if r["id"] == rid)

        lines = [f"[검증 결과] {row.get('result', '')}"]
        d = row.get("def")
        if d:
            lines.append(f"[정의서] {d.ref}  {d.title()}  (상태: {d.state or '-'})")
            for k, v in d.expected.items():
                lines.append(f"    {k}: {v}")
        for lvl, msg in row.get("issues", []):
            lines.append(f"  - ({lvl}) {msg}")
        if row.get("chain_note"):
            lines.append(f"  · {row['chain_note']}")

        tx = row["fields"].get("log_tx", "")
        if tx and tx != "0":
            group = [r for r in self.data_rows if r["fields"].get("log_tx") == tx]
            lines += ["", f"[같은 log_tx={tx} 로그 {len(group)}건]"]
            for g in sorted(group, key=lambda r: lv.to_num(r["fields"].get("modTime")) or 0):
                f = g["fields"]
                val = ""
                if g["로그타입"] == "item":
                    val = f"{f.get('itemType')} {f.get('itemId')}: {f.get('quantityBefore')} → {f.get('quantityAfter')} ({f.get('modType')} {f.get('quantity')})"
                elif g["로그타입"] in ("cashitem", "resource"):
                    val = f"{f.get('rCurrency')}: {f.get('amountBefore')} → {f.get('amount')} (delta {f.get('delta')})"
                elif g["로그타입"] == "action":
                    val = f"{f.get('category')}/{f.get('label')}/{f.get('action')}"
                lines.append(f"  {g['로그타입']:<9} {g['reason']:<24} {val}  [{g.get('result', '')}]")

        lines += ["", "[로그 필드]"]
        lines += [f"  {k} = {v}" for k, v in row["fields"].items()]
        lines += ["", "[원문]", row["로그정보"]]

        win = tk.Toplevel(self)
        win.title(f"로그 상세 (id={rid}, {row['로그시간']} {row['로그타입']} {row['reason']})")

        txt = ScrolledText(win, width=140, height=40)
        txt.pack(fill="both", expand=True)
        txt.insert(tk.END, "\n".join(lines))

    # -------------------- 필터 (텍스트 AND reason AND 검증결과) --------------------
    def apply_filters(self):
        kw = self.ent_filter.get().strip().lower()
        rkw = self.ent_reason_filter.get().strip().lower()
        res = self.cmb_result.get()

        def ok(r):
            if kw and kw not in " ".join(str(r[k]) for k in (
                    "게임명", "App ID", "로그시간", "로그타입", "태그1", "reason", "로그정보")).lower() \
                    + " " + r.get("detail", "").lower():
                return False
            if rkw and rkw not in r["reason"].lower():
                return False
            if res == RESULT_FILTERS[1]:
                return r.get("result") in (lv.RESULT_FAIL, lv.RESULT_UNDEF, lv.RESULT_WARN)
            if res and res != RESULT_FILTERS[0]:
                return r.get("result") == res
            return True

        self.filtered_rows = [r for r in self.data_rows if ok(r)]
        self.refresh_table()

    def reset_filter(self):
        self.ent_filter.delete(0, tk.END)
        self.ent_reason_filter.delete(0, tk.END)
        self.cmb_result.current(0)
        self.apply_filters()

    # -------------------- 정의서에 결과 기입 --------------------
    def write_to_definition(self):
        if not self.definition:
            messagebox.showwarning("알림", "먼저 '2) 로그정의서 로드'를 해주세요.")
            return
        if not self.data_rows:
            messagebox.showwarning("알림", "크롤링된 로그가 없습니다.")
            return

        src = Path(self.definition.path)
        path = filedialog.asksaveasfilename(
            title="결과를 기입할 정의서 사본 저장",
            initialdir=str(src.parent),
            initialfile=f"{src.stem}_자동검수_{datetime.now():%Y%m%d_%H%M}.xlsx",
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx")],
        )
        if not path:
            return
        try:
            s = lv.write_results(src, path, self.data_rows, self.definition)
        except PermissionError:
            messagebox.showerror("저장 실패", f"파일이 다른 프로그램(Excel 등)에서 열려 있습니다.\n닫고 다시 시도해주세요.\n\n{path}")
            return
        except Exception as e:
            messagebox.showerror("저장 실패", f"{e}\n\n{path}")
            return

        undef = sum(1 for r in self.data_rows if r.get("result") == lv.RESULT_UNDEF)
        msg = (f"정의서 {s['rows']}개 행에 결과 기입 (Pass {s['pass']} / Fail {s['fail']} 칸)\n"
               f"정의서에 없는 로그 {undef}건은 '{lv.LOG_SHEET_NAME}' 시트에서 확인하세요.\n\n{path}")
        self.log("✔ " + msg.replace("\n", " "))
        messagebox.showinfo("기입 완료", msg)

    # -------------------- Excel 저장 --------------------
    def _export_df(self, rows):
        return pd.DataFrame([{
            "게임명": r["게임명"], "App ID": r["App ID"], "로그시간": r["로그시간"],
            "로그타입": r["로그타입"], "태그1": r["태그1"], "reason": r["reason"],
            "검증결과": r.get("result", ""), "검증상세": r.get("detail", ""),
            "정의서 위치": r["def"].ref if r.get("def") else "",
            "로그정보": r["로그정보"],
        } for r in rows])

    def save_all_to_excel(self):
        if not self.data_rows:
            messagebox.showwarning("저장 불가", "데이터 없음")
            return

        df = self._export_df(self.data_rows)
        path = filedialog.asksaveasfilename(defaultextension=".xlsx")
        if not path:
            return

        if self._write_excel(df, path):
            messagebox.showinfo("저장 완료", f"저장됨:\n{path}")

    def _write_excel(self, df, path) -> bool:
        try:
            df.to_excel(path, index=False)
            self.log(f"✔ Excel 저장: {path} ({len(df)}행)")
            return True
        except PermissionError:
            messagebox.showerror("저장 실패", f"파일이 다른 프로그램(Excel 등)에서 열려 있습니다.\n닫고 다시 시도해주세요.\n\n{path}")
        except Exception as e:
            messagebox.showerror("저장 실패", f"{e}\n\n{path}")
        return False

    def save_checked_to_excel(self):
        checked = [r for r in self.data_rows if r["checked"]]

        if not checked:
            messagebox.showwarning("저장 불가", "체크된 항목 없음")
            return

        df = self._export_df(checked)
        path = filedialog.asksaveasfilename(defaultextension=".xlsx")
        if not path:
            return

        if self._write_excel(df, path):
            messagebox.showinfo("저장 완료", f"체크된 항목 저장됨:\n{path}")

    # -------------------- 통계 --------------------
    def show_reason_stats(self):
        if not self.data_rows:
            messagebox.showwarning("데이터 없음")
            return

        lines = ["=== 검증 결과 ==="]
        for k, v in Counter(r.get("result", "") for r in self.data_rows).most_common():
            lines.append(f"{k} : {v}건")

        issue_cnt = Counter()
        for r in self.data_rows:
            for lvl, msg in r.get("issues", []):
                # 수치가 들어간 메시지는 유형별로 묶기
                issue_cnt[re.split(r"[:(]", msg)[0].strip()] += 1
        if issue_cnt:
            lines.append("\n=== 문제 유형 ===")
            for k, v in issue_cnt.most_common():
                lines.append(f"{k} : {v}건")

        counter = Counter(r["reason"] or "(reason 없음)" for r in self.data_rows)
        lines.append("\n=== reason 통계 ===")
        for k, v in counter.most_common():
            lines.append(f"{k} : {v}건")

        win = tk.Toplevel(self)
        win.title("통계")

        txt = ScrolledText(win, width=90, height=34)
        txt.pack(fill="both", expand=True)
        txt.insert(tk.END, "\n".join(lines))


# --------------------------- main ---------------------------
if __name__ == "__main__":
    app = LogCrawlerGUI()
    app.mainloop()
