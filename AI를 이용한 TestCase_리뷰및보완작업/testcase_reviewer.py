import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pandas as pd
import openpyxl
from typing import List, Dict, Any
import json
from anthropic import Anthropic
from pathlib import Path
import time
import threading

class ProgressDialog:
    def __init__(self, parent):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("리뷰 진행 중")
        self.dialog.geometry("300x150")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        main_frame = ttk.Frame(self.dialog, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        self.status_label = ttk.Label(main_frame, text="TestCase 리뷰를 진행 중입니다...")
        self.status_label.pack(pady=10)
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(main_frame, 
                                          variable=self.progress_var,
                                          maximum=100,
                                          mode='determinate')
        self.progress_bar.pack(fill=tk.X, pady=5)
        
        self.progress_label = ttk.Label(main_frame, text="0/0 TestCases 처리됨")
        self.progress_label.pack(pady=5)
        
        self.center_window()
    
    def update_progress(self, current, total):
        self.progress_var.set((current / total) * 100)
        self.progress_label.config(text=f"{current}/{total} TestCases 처리됨")
        self.dialog.update()
    
    def center_window(self):
        self.dialog.update_idletasks()
        width = self.dialog.winfo_width()
        height = self.dialog.winfo_height()
        x = (self.dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (height // 2)
        self.dialog.geometry(f'+{x}+{y}')

    def destroy(self):
        self.progress_bar.stop()
        self.dialog.destroy()

class ErrorDialog:
    def __init__(self, parent, message="TestCase 리뷰 실패"):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("오류")
        self.dialog.geometry("250x100")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        self.dialog.overrideredirect(True)
        
        main_frame = ttk.Frame(self.dialog, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        error_label = ttk.Label(main_frame, text="❌", font=("Arial", 20))
        error_label.pack(pady=5)
        
        message_label = ttk.Label(main_frame, text=message)
        message_label.pack(pady=5)
        
        ok_button = ttk.Button(main_frame, text="확인", command=self.dialog.destroy)
        ok_button.pack(pady=5)
        
        self.center_window()
        
    def center_window(self):
        self.dialog.update_idletasks()
        width = self.dialog.winfo_width()
        height = self.dialog.winfo_height()
        x = (self.dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (height // 2)
        self.dialog.geometry(f'+{x}+{y}')

class TestCaseReviewer:
    def __init__(self, api_key: str):
        self.excel_path = None
        self.workbook = None
        self.sheet_names = []
        self.current_sheet = None
        self.test_cases = None
        self.anthropic = Anthropic(api_key=api_key)

    def load_excel(self) -> list:
        try:
            df = pd.read_excel(self.excel_path, sheet_name=None)
            self.sheet_names = list(df.keys())
            return self.sheet_names
        except Exception as e:
            print(f"엑셀 파일 로드 중 오류 발생: {str(e)}")
            return []

    def select_sheet(self, sheet_name: str) -> bool:
        try:
            df = pd.read_excel(
                self.excel_path,
                sheet_name=sheet_name,
                skiprows=14
            )
            
            df.columns = [str(col).strip() for col in df.columns]
            
            self.test_cases = []
            for _, row in df.iterrows():
                testcase = {
                    'ID': str(row['ID']),
                    'DEPTH1': str(row['DEPTH1']) if pd.notna(row['DEPTH1']) else '',
                    'DEPTH2': str(row['DEPTH2']) if pd.notna(row['DEPTH2']) else '',
                    'DEPTH3': str(row['DEPTH3']) if pd.notna(row['DEPTH3']) else '',
                    'Precondition': str(row['Precondition']) if pd.notna(row['Precondition']) else '',
                    'Step': str(row['Step']) if pd.notna(row['Step']) else '',
                    'Expected_Result': str(row['Expected Result']) if pd.notna(row['Expected Result']) else ''
                }
                self.test_cases.append(testcase)
            
            print(f"{len(self.test_cases)}개의 TestCase를 로드했습니다.")
            return True
            
        except Exception as e:
            print(f"시트 데이터 로드 중 오류 발생: {str(e)}")
            return False

    def review_with_claude(self) -> list:
        if not self.test_cases:
            return [{"error": "리뷰할 TestCase가 없습니다."}]

        review_results = []
        batch_size = 3
        total_cases = len(self.test_cases)
        auto_save_interval = 15
        
        for i in range(0, total_cases, batch_size):
            batch = self.test_cases[i:i+batch_size]
            current_batch = min(i+batch_size, total_cases)
            print(f"배치 처리 중: {i+1}~{current_batch} / {total_cases}")
            
            batch_prompt = "다음 TestCase들을 간단히 분석하고 개선점을 제시해주세요:\n\n"
            for test_case in batch:
                if test_case['ID'].strip():
                    batch_prompt += f"[ID:{test_case['ID']}]\nDEPTH: {test_case.get('DEPTH1', '')} > {test_case.get('DEPTH2', '')} > {test_case.get('DEPTH3', '')}\n전제조건: {test_case.get('Precondition', '')}\n단계: {test_case.get('Step', '')}\n예상결과: {test_case.get('Expected_Result', '')}\n\n"

            batch_prompt += """각 TestCase의 분석 결과를 다음 JSON 형식으로 응답해주세요:
    {
        "test_case_reviews": [
            {
                "id": "TestCase ID",
                "analysis": {
                    "depth": {"issues": [], "suggestions": []},
                    "precondition": {"issues": [], "suggestions": []},
                    "steps": {"issues": [], "suggestions": []},
                    "expected": {"issues": [], "suggestions": []}
                },
                "improved": {
                    "DEPTH1": "",
                    "DEPTH2": "",
                    "DEPTH3": "",
                    "Precondition": "",
                    "Step": "",
                    "Expected_Result": ""
                }
            }
        ]
    }"""

            try:
                message = self.anthropic.messages.create(
                    model="claude-3-opus-20240229",
                    max_tokens=2000,
                    temperature=0,
                    messages=[{"role": "user", "content": batch_prompt}]
                )
                
                try:
                    response_text = message.content[0].text
                    json_start = response_text.find('{')
                    json_end = response_text.rfind('}') + 1
                    
                    if json_start >= 0 and json_end > json_start:
                        parsed_result = json.loads(response_text[json_start:json_end])
                        
                        if 'test_case_reviews' in parsed_result:
                            for review in parsed_result['test_case_reviews']:
                                review_results.append({
                                    "test_case_id": review['id'],
                                    "depth_review": review['analysis']['depth'],
                                    "precondition_review": review['analysis']['precondition'],
                                    "step_review": review['analysis']['steps'],
                                    "expected_result_review": review['analysis']['expected'],
                                    "improved_test_case": review['improved'],
                                    "original_response": response_text
                                })
                                
                                current_progress = len(review_results)
                                print(f"처리된 TestCase: {current_progress}/{total_cases}")
                
                except json.JSONDecodeError as je:
                    print(f"JSON 파싱 오류 (배치 {i+1}~{current_batch}): {str(je)}")
                    print("원본 응답:", response_text)
                
                time.sleep(0.5)
                    
            except Exception as e:
                print(f"배치 처리 중 오류 발생 (배치 {i+1}~{current_batch}): {str(e)}")
                for test_case in batch:
                    if test_case['ID'].strip():
                        review_results.append({
                            "test_case_id": test_case['ID'],
                            "error": str(e),
                            "improved_test_case": test_case.copy()
                        })

        return review_results

    # TestCaseReviewer 클래스의 save_improved_test_cases 메소드 수정
    def save_improved_test_cases(self, output_path: str, review_results: list):
        try:
            # 데이터프레임 생성을 위한 리스트
            save_data = []
            
            for result in review_results:
                if isinstance(result, dict):
                    row_data = {}
                    
                    # 기본 정보 저장
                    if 'test_case_id' in result:
                        row_data['ID'] = result['test_case_id']
                    
                    # 개선된 내용 저장
                    if 'improved_test_case' in result:
                        improved = result['improved_test_case']
                        row_data.update({
                            'DEPTH1': improved.get('DEPTH1', ''),
                            'DEPTH2': improved.get('DEPTH2', ''),
                            'DEPTH3': improved.get('DEPTH3', ''),
                            'Precondition': improved.get('Precondition', ''),
                            'Step': improved.get('Step', ''),
                            'Expected Result': improved.get('Expected_Result', '')
                        })
                    
                    # 리뷰 코멘트 생성
                    comments = []
                    sections = {
                        'depth_review': 'DEPTH 구조',
                        'precondition_review': '전제조건',
                        'step_review': '테스트 단계',
                        'expected_result_review': '예상 결과'
                    }
                    
                    for key, section_name in sections.items():
                        if key in result:
                            section = result[key]
                            if isinstance(section, dict):
                                if section.get('issues') or section.get('suggestions'):
                                    comments.append(f"[{section_name}]")
                                    
                                    if section.get('issues'):
                                        comments.append("문제점:")
                                        comments.extend([f"- {issue}" for issue in section['issues']])
                                    
                                    if section.get('suggestions'):
                                        comments.append("개선사항:")
                                        comments.extend([f"- {suggestion}" for suggestion in section['suggestions']])
                    
                    row_data['Review_Comments'] = "\n".join(comments)
                    save_data.append(row_data)
            
            # DataFrame 생성
            final_df = pd.DataFrame(save_data)
            
            # 파일 저장
            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                final_df.to_excel(writer, sheet_name='Review_Result', index=False)
            
            print(f"리뷰 결과가 {output_path}에 저장되었습니다.")
            return True
            
        except Exception as e:
            print(f"결과 저장 중 오류 발생: {str(e)}")
            return False

    def save_interim_results(self, results: list, output_path: str = None):
        if not output_path:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            output_path = f"review_interim_{timestamp}.json"
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'sheet_name': self.current_sheet,
                    'total_cases': len(self.test_cases),
                    'reviewed_cases': len(results),
                    'results': results
                }, f, ensure_ascii=False, indent=2)
            print(f"중간 결과가 {output_path}에 저장되었습니다.")
            return True
        except Exception as e:
            print(f"중간 결과 저장 중 오류 발생: {str(e)}")
            return False

class TestCaseReviewerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("TestCase Reviewer")
        self.root.geometry("800x600")
        
        self.api_key = None
        self.reviewer = None
        self.excel_path = None
        self.config_file = Path("api_config.json")
        
        self.create_widgets()
        self.load_saved_api_key()

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # API Key Frame
        api_frame = ttk.LabelFrame(main_frame, text="API Key", padding="5")
        api_frame.pack(fill=tk.X, pady=(0, 5))
        
        api_input_frame = ttk.Frame(api_frame)
        # create_widgets 메소드 계속...
        api_input_frame.pack(fill=tk.X)
        
        self.api_key_var = tk.StringVar()
        self.api_key_entry = ttk.Entry(api_input_frame, textvariable=self.api_key_var, width=60)
        self.api_key_entry.pack(side=tk.LEFT, padx=5)
        
        self.save_api_var = tk.BooleanVar(value=True)
        save_check = ttk.Checkbutton(api_input_frame, text="저장", variable=self.save_api_var)
        save_check.pack(side=tk.LEFT)
        
        api_save_btn = ttk.Button(api_input_frame, text="API 설정", command=self.set_api_key)
        api_save_btn.pack(side=tk.LEFT, padx=5)
        
        # 파일 선택 프레임
        file_frame = ttk.LabelFrame(main_frame, text="엑셀 파일 선택", padding="5")
        file_frame.pack(fill=tk.X, pady=5)
        
        self.file_path_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.file_path_var, width=60).pack(side=tk.LEFT, padx=5)
        ttk.Button(file_frame, text="찾아보기", command=self.select_file).pack(side=tk.LEFT)
        
        # 시트 선택 프레임
        sheet_frame = ttk.LabelFrame(main_frame, text="시트 선택", padding="5")
        sheet_frame.pack(fill=tk.X, pady=5)
        
        self.sheet_listbox = tk.Listbox(sheet_frame, height=5)
        self.sheet_listbox.pack(fill=tk.X)
        
        # 리뷰 결과 프레임
        result_frame = ttk.LabelFrame(main_frame, text="리뷰 결과", padding="5")
        result_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        scrollbar = ttk.Scrollbar(result_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.result_text = tk.Text(result_frame, wrap=tk.WORD, height=20, yscrollcommand=scrollbar.set)
        self.result_text.pack(fill=tk.BOTH, expand=True)
        
        scrollbar.config(command=self.result_text.yview)
        
        # 버튼 프레임
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(button_frame, text="리뷰 시작", command=self.start_review).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="중간 저장", command=self.save_interim).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="결과 저장", command=self.save_results).pack(side=tk.LEFT, padx=5)

    def save_interim(self):
        if not self.result_text.get(1.0, tk.END).strip():
            messagebox.showerror("오류", "저장할 중간 결과가 없습니다.")
            return
            
        try:
            review_results = json.loads(self.result_text.get(1.0, tk.END))
            
            file_path = filedialog.asksaveasfilename(
                title="중간 결과 저장",
                defaultextension=".json",
                filetypes=[("JSON files", "*.json")]
            )
            
            if file_path and self.reviewer:
                if self.reviewer.save_interim_results(review_results, file_path):
                    messagebox.showinfo("성공", "중간 결과가 저장되었습니다.")
                else:
                    messagebox.showerror("오류", "중간 결과 저장 실패")
        except Exception as e:
            messagebox.showerror("오류", f"중간 결과 저장 중 오류 발생: {str(e)}")

    def load_saved_api_key(self):
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    saved_key = config.get('api_key')
                    if saved_key:
                        self.api_key_var.set(saved_key)
            except Exception as e:
                messagebox.showerror("오류", f"API 키 로드 중 오류 발생: {e}")

    def save_api_key(self, api_key):
        if self.save_api_var.get():
            try:
                with open(self.config_file, 'w') as f:
                    json.dump({'api_key': api_key}, f)
            except Exception as e:
                messagebox.showerror("오류", f"API 키 저장 중 오류 발생: {e}")

    def set_api_key(self):
        api_key = self.api_key_var.get().strip()
        if not api_key:
            messagebox.showerror("오류", "API Key를 입력해주세요.")
            return
        
        if not api_key.startswith('sk-'):
            messagebox.showerror("오류", "유효하지 않은 API 키 형식입니다.")
            return
            
        try:
            anthropic = Anthropic(api_key=api_key)
            test_message = anthropic.messages.create(
                model="claude-3-opus-20240229",
                max_tokens=10,
                messages=[{"role": "user", "content": "Test"}]
            )
            self.reviewer = TestCaseReviewer(api_key)
            self.save_api_key(api_key)
            messagebox.showinfo("성공", "API Key가 성공적으로 설정되었습니다.")
        except Exception as e:
            messagebox.showerror("오류", f"API 키 검증 실패: {str(e)}")

    def select_file(self):
        file_path = filedialog.askopenfilename(
            title="TestCase 엑셀 파일 선택",
            filetypes=[("Excel files", "*.xlsx *.xls")]
        )
        
        if file_path:
            self.excel_path = file_path
            self.file_path_var.set(file_path)
            self.load_sheet_names()

    def load_sheet_names(self):
        if not self.reviewer:
            messagebox.showerror("오류", "먼저 API Key를 설정해주세요.")
            return
            
        try:
            self.reviewer.excel_path = self.excel_path
            sheet_names = self.reviewer.load_excel()
            self.sheet_listbox.delete(0, tk.END)
            for sheet_name in sheet_names:
                self.sheet_listbox.insert(tk.END, sheet_name)
        except Exception as e:
            messagebox.showerror("오류", f"시트 목록 로드 실패: {e}")

    def start_review(self):
        if not self.reviewer:
            messagebox.showerror("오류", "먼저 API Key를 설정해주세요.")
            return
            
        if not self.excel_path:
            messagebox.showerror("오류", "엑셀 파일을 선택해주세요.")
            return
            
        selection = self.sheet_listbox.curselection()
        if not selection:
            messagebox.showerror("오류", "시트를 선택해주세요.")
            return
            
        sheet_name = self.sheet_listbox.get(selection[0])
        
        try:
            # 진행 상태 다이얼로그 표시
            self.progress_dialog = ProgressDialog(self.root)
            self.root.update()
            
            def review_process():
                try:
                    if self.reviewer.select_sheet(sheet_name):
                        results = self.reviewer.review_with_claude()
                        self.root.after(0, lambda: self._update_review_results(results))
                    else:
                        self.root.after(0, lambda: self._handle_review_error("시트 데이터 로드 실패"))
                except Exception as e:
                    self.root.after(0, lambda: self._handle_review_error(str(e)))

            self.review_thread = threading.Thread(target=review_process, daemon=True)
            self.review_thread.start()
                
        except Exception as e:
            if hasattr(self, 'progress_dialog'):
                self.progress_dialog.destroy()
            ErrorDialog(self.root, f"리뷰 중 오류 발생: {str(e)}")

    def _update_review_results(self, results):
        try:
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, json.dumps(results, indent=2, ensure_ascii=False))
        finally:
            if hasattr(self, 'progress_dialog'):
                self.progress_dialog.destroy()

    def _handle_review_error(self, error_msg):
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.destroy()
        ErrorDialog(self.root, f"리뷰 실패: {error_msg}")

    def save_results(self):
        if not self.result_text.get(1.0, tk.END).strip():
            messagebox.showerror("오류", "저장할 리뷰 결과가 없습니다.")
            return
            
        try:
            review_results = json.loads(self.result_text.get(1.0, tk.END))
            
            if not isinstance(review_results, list):
                review_results = [review_results]
                
            if not review_results:
                messagebox.showerror("오류", "저장할 리뷰 결과가 없습니다.")
                return
            
            file_path = filedialog.asksaveasfilename(
                title="리뷰 결과 저장",
                defaultextension=".xlsx",
                filetypes=[("Excel files", "*.xlsx")]
            )
            
            if file_path and self.reviewer:
                if self.reviewer.save_improved_test_cases(file_path, review_results):
                    messagebox.showinfo("성공", "리뷰 결과가 저장되었습니다.")
                else:
                    messagebox.showerror("오류", "리뷰 결과 저장에 실패했습니다.")
                    
        except json.JSONDecodeError:
            messagebox.showerror("오류", "리뷰 결과 형식이 올바르지 않습니다.")
        except Exception as e:
            messagebox.showerror("오류", f"저장 중 오류 발생: {str(e)}")

def main():
    root = tk.Tk()
    app = TestCaseReviewerGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()