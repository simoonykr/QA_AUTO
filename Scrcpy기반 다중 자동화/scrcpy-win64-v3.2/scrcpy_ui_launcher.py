import subprocess
import tkinter as tk
from tkinter import messagebox, filedialog
import threading
import time
import os

apk_path = ""
test_script_path = ""
report_lines = []

test_mode = None

# ✅ 중복 실행 방지용 캐시 전역으로 선언
executed_devices = set()
test_started = False  # ✅ 중복 테스트 호출 자체 차단

def get_connected_devices():
    result = subprocess.run(["adb", "devices"], capture_output=True, text=True)
    lines = result.stdout.strip().split("\n")[1:]
    devices = [line.split("\t")[0] for line in lines if "device" in line]
    return list(dict.fromkeys(devices))

def select_apk():
    global apk_path
    apk_path = filedialog.askopenfilename(filetypes=[("APK files", "*.apk")])
    if apk_path:
        log_text.insert(tk.END, f"[*] Selected APK: {apk_path}\n")

def install_and_launch_apk():
    thread = threading.Thread(target=install_apk_thread)
    thread.start()

def install_apk_thread():
    if not apk_path:
        messagebox.showerror("Error", "Please select an APK file first.")
        return

    devices = get_connected_devices()
    for device in devices:
        log_text.insert(tk.END, f"[*] Installing APK on {device}...\n")
        result = subprocess.run(["adb", "-s", device, "install", "-r", apk_path], capture_output=True, text=True)
        if "Success" in result.stdout:
            log_text.insert(tk.END, f"[+] APK installed successfully on {device}.\n")
        else:
            log_text.insert(tk.END, f"[X] APK install failed on {device}: {result.stdout}\n")

def select_test_script():
    global test_script_path
    path = filedialog.askopenfilename(filetypes=[("Python files", "*.py")])
    if path:
        test_script_path = path
        log_text.insert(tk.END, f"[*] Selected Test Script: {test_script_path}\n")

def run_test_by_mode():
        run_image_test()


def run_image_test():
    if not test_script_path or not os.path.exists(test_script_path):
        messagebox.showerror("Error", "Please select a valid image test script first.")
        return

    devices = get_connected_devices()
    for device in devices:
        log_text.insert(tk.END, f"[*] Starting Image-based test on {device}...\n")
        run_image_script(device)

def run_image_script(device_id):
    try:
        # scrcpy 실행
        scrcpy_process = subprocess.Popen([
            "scrcpy",
            "-s", device_id,
            "--no-audio",
            "--window-title", f"Device {device_id}"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        time.sleep(2)  # 화면 뜰 시간 대기

        # 테스트 실행
        subprocess.run(["python", test_script_path, "--device-id", device_id])
        log_text.insert(tk.END, f"[✓] Image-based test completed on {device_id}\n")
        report_lines.append(f"[✓] Image-based test completed on {device_id}")

    except Exception as e:
        log_text.insert(tk.END, f"[X] Image-based test failed on {device_id}: {e}\n")
        report_lines.append(f"[X] Image-based test failed on {device_id}: {e}")

    finally:
        subprocess.call(["taskkill", "/F", "/IM", "scrcpy.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)



def save_report():
    if not report_lines:
        messagebox.showinfo("Info", "No report data to save.")
        return
    report_path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[["Text files", "*.txt"]])
    if report_path:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(report_lines))
        messagebox.showinfo("Success", f"Report saved to {report_path}")

def stop_all_scrcpy():
    subprocess.call("taskkill /F /IM scrcpy.exe", shell=True)
    log_text.insert(tk.END, "[!] All scrcpy processes killed.\n")

def run_all():
    log_text.delete("1.0", tk.END)
    devices = get_connected_devices()
    port = 27180
    for device in devices:
        port += 1
        log_text.insert(tk.END, f"[>] Connecting to {device} (port {port})...\n")
        try:
            subprocess.Popen([
                "scrcpy",
                "-s", device,
                "--no-audio",
                f"--port={port}",
                f"--window-title=Device {device}"
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            log_text.insert(tk.END, f"[+] Connected: {device}\n")
        except Exception as e:
            log_text.insert(tk.END, f"[X] Failed to connect {device}: {e}\n")

def refresh_device_list():
    device_listbox.delete(0, tk.END)
    devices = get_connected_devices()
    for device in devices:
        device_listbox.insert(tk.END, device)

def run_selected_device():
    selection = device_listbox.curselection()
    if not selection:
        messagebox.showwarning("Warning", "Please select a device to run.")
        return
    selected = device_listbox.get(selection[0])
    port = 28000
    log_text.insert(tk.END, f"[>] Running scrcpy for selected device: {selected}\n")
    try:
        subprocess.Popen([
            "scrcpy",
            "-s", selected,
            "--no-audio",
            f"--port={port}",
            f"--window-title=Device {selected}"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log_text.insert(tk.END, f"[+] Connected: {selected}\n")
    except Exception as e:
        log_text.insert(tk.END, f"[X] Failed to connect {selected}: {e}\n")


root = tk.Tk()
root.title("scrcpy Device image_automation Launcher")
root.geometry("800x600")

frame = tk.Frame(root)
frame.pack(pady=10)

device_listbox = tk.Listbox(root, height=6)
device_listbox.pack(fill=tk.X, padx=10, pady=(0,10))

log_text = tk.Text(root, wrap=tk.WORD, font=("Courier", 10))
log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)


tk.Button(frame, text="① Run scrcpy on all devices", command=run_all).grid(row=0, column=0, padx=5)
tk.Button(frame, text="✖ Stop All scrcpy", command=stop_all_scrcpy).grid(row=0, column=1, padx=5)
tk.Button(frame, text="↻ Refresh Devices", command=refresh_device_list).grid(row=0, column=2, padx=5)
tk.Button(frame, text="▶ Run Selected Device", command=run_selected_device).grid(row=0, column=3, padx=5)
tk.Button(frame, text="② Select APK", command=select_apk).grid(row=1, column=0, padx=5)
tk.Button(frame, text="③ Install && Launch APK", command=install_and_launch_apk).grid(row=1, column=1, padx=5)
tk.Button(frame, text="④ Select Test Script", command=select_test_script).grid(row=1, column=2, padx=5)
#tk.Button(frame, text="⑤ Start Appium Servers", command=start_appium_servers).grid(row=1, column=3, padx=5)
tk.Button(frame, text="⑥ Run Selected Test", command=run_test_by_mode).grid(row=2, column=0, padx=5, pady=5)
tk.Button(frame, text="⑦ Save Report", command=save_report).grid(row=2, column=1, padx=5, pady=5)

refresh_device_list()
root.mainloop()
