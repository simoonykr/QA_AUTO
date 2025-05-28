
import cv2
import pyautogui
import pandas as pd
import time
import argparse
import numpy as np
from PIL import ImageGrab
from datetime import datetime
from tkinter import filedialog, Tk
import os

# HTML 리포트 생성 함수
def generate_html_report(results_dict):
    now = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    filename = f"report_{now}.html"
    with open(filename, "w", encoding="utf-8") as f:
        f.write("<html><head><meta charset='utf-8'><title>테스트 결과 리포트</title></head><body>")
        f.write(f"<h1>📋 디바이스 테스트 결과 ({now})</h1><hr>")
        for device, logs in results_dict.items():
            f.write(f"<h2>📱 디바이스: {device}</h2><ul>")
            for line in logs:
                color = "green" if "✓" in line else "red" if "X" in line else "black"
                f.write(f"<li style='color:{color}'>{line}</li>")
            f.write("</ul><hr>")
        f.write("</body></html>")
    print(f"[📁] HTML 리포트 저장됨: {filename}")

# 다중 스케일 매칭 + 하이라이트 표시
def find_best_match_with_scales(screen_path, template_path, threshold=0.8, show_highlight=True):
    screen = cv2.imread(screen_path)
    template = cv2.imread(template_path)

    if screen is None or template is None:
        print(f"[X] 이미지 로드 실패 - screen: {screen_path}, template: {template_path}")
        return None

    gray_screen = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)

    best_val = 0
    best_center = None
    best_rect = None
    scales = [1.0, 0.9, 1.1, 0.8, 1.2]

    for scale in scales:
        resized_template = cv2.resize(template, (0, 0), fx=scale, fy=scale)
        gray_template = cv2.cvtColor(resized_template, cv2.COLOR_BGR2GRAY)

        result = cv2.matchTemplate(gray_screen, gray_template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val > best_val and max_val >= threshold:
            h, w = gray_template.shape
            best_center = (max_loc[0] + w // 2, max_loc[1] + h // 2)
            best_rect = (max_loc[0], max_loc[1], w, h)
            best_val = max_val

    if best_center and show_highlight:
        x, y, w, h = best_rect
        highlight = screen.copy()
        cv2.rectangle(highlight, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.imshow("🎯 인식 위치 하이라이트", highlight)
        cv2.waitKey(800)
        cv2.destroyAllWindows()

    if best_center:
        print(f"[✓] 최적 인식 성공 - 유사도: {best_val:.3f} 위치: {best_center}")
        return best_center

    print(f"[X] 인식 실패 (모든 스케일) - {template_path}")
    return None

# 디바이스 ID 파라미터
parser = argparse.ArgumentParser()
parser.add_argument('--device-id', required=True, help='ADB 디바이스 ID')
args = parser.parse_args()
device_id = args.device_id

# 엑셀 선택 다이얼로그
root = Tk()
root.withdraw()
excel_path = filedialog.askopenfilename(title="📂 엑셀 파일 선택", filetypes=[("Excel files", "*.xlsx")])
if not excel_path or not os.path.exists(excel_path):
    print("[X] 엑셀 파일을 선택하지 않았거나 파일이 존재하지 않습니다.")
    exit()

df = pd.read_excel(excel_path)
results = {device_id: []}

for index, row in df.iterrows():
    image_path = row['image_path']
    offset_x = int(row.get('offset_x', 0))
    offset_y = int(row.get('offset_y', 0))
    action = row['action']
    wait_sec = float(row.get('wait_sec', 1))
    text_to_write = str(row.get('write', ''))

    screen_path = "screen_temp.png"
    screen = ImageGrab.grab()
    screen.save(screen_path)

    location = find_best_match_with_scales(screen_path, image_path)
    if location is None:
        msg = f"[X] 이미지 인식 실패: {image_path}"
        print(msg)
        results[device_id].append(msg)
        continue
    else:
        msg = f"[✓] 이미지 인식 성공: {image_path} 위치: {location}"
        print(msg)
        results[device_id].append(msg)

    target_x = location[0] + offset_x
    target_y = location[1] + offset_y

    if action == "click":
        pyautogui.click(target_x, target_y)
        msg = f"[{device_id}] 🖱 클릭 - {image_path}"
        print(msg)
        results[device_id].append(msg)

    elif action == "write":
        pyautogui.click(target_x, target_y)
        time.sleep(0.5)
        pyautogui.write(text_to_write, interval=0.05)
        msg = f"[{device_id}] ⌨ 입력 - {text_to_write}"
        print(msg)
        results[device_id].append(msg)

    time.sleep(wait_sec)

generate_html_report(results)
