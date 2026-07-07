# performance_monitor.py
import time
import threading
from datetime import datetime
from collections import deque
import pandas as pd
import numpy as np
from typing import Dict, Optional

from config import config
from exceptions import PerformanceMonitorError
from logger import logger
class PerformanceData:
    def __init__(self):
        self.fps = deque(maxlen=config.MAX_DATA_POINTS)
        self.cpu = deque(maxlen=config.MAX_DATA_POINTS)
        self.memory = deque(maxlen=config.MAX_DATA_POINTS)
        self.timestamps = deque(maxlen=config.MAX_DATA_POINTS)
        
    def add_data(self, fps: float, cpu: float, memory: float):
        """새로운 성능 데이터 추가"""
        self.fps.append(fps)
        self.cpu.append(cpu)
        self.memory.append(memory)
        self.timestamps.append(datetime.now())
        
    def to_dataframe(self) -> pd.DataFrame:
        """성능 데이터를 DataFrame으로 변환"""
        return pd.DataFrame({
            'Timestamp': list(self.timestamps),
            'FPS': list(self.fps),
            'CPU': list(self.cpu),
            'Memory': list(self.memory)
        })

class PerformanceMonitor:
    def __init__(self, adb_controller):
        self.adb = adb_controller
        self.data = PerformanceData()
        self.selected_app = None
        self.monitoring = False
        self.monitoring_thread = None
        
    def start_monitoring(self):
        """성능 모니터링 시작"""
        if not self.selected_app:
            raise PerformanceMonitorError("모니터링할 앱이 선택되지 않았습니다.")
            
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            return
            
        self.monitoring = True
        self.monitoring_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitoring_thread.start()
        
    def stop_monitoring(self):
        """성능 모니터링 중지"""
        self.monitoring = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=1.0)  # 최대 1초 대기
        
    def _monitor_loop(self):
        """성능 모니터링 루프"""
        while self.monitoring:
            try:
                fps = self._get_fps()
                cpu = self._get_cpu()
                memory = self._get_memory()
                
                self.data.add_data(fps, cpu, memory)
                
                # 경고 조건 확인
                self._check_warnings(fps, cpu, memory)
                
                time.sleep(config.MONITORING_INTERVAL)
                
            except Exception as e:
                logger.error(f"성능 모니터링 오류: {e}")
                raise PerformanceMonitorError(f"성능 모니터링 오류: {e}")
                
    def _get_fps(self) -> float:
        """FPS 측정"""
        try:
            result = self.adb.execute_command(
                f'adb shell dumpsys gfxinfo {self.selected_app} framestats'
            )
            return self._parse_fps(result)
        except Exception as e:
            logger.error(f"FPS 측정 실패: {e}")
            return 0.0

    def _get_cpu(self) -> float:
        """CPU 사용량 측정"""
        try:
            # 프로세스 ID 가져오기
            pid_cmd = f'adb shell pidof {self.selected_app}'
            pid = self.adb.execute_command(pid_cmd)
            pid = pid.strip()

            if not pid:
                return 0.0

            # CPU 상태 측정
            cpu_before = self.adb.execute_command('adb shell cat /proc/stat')
            proc_before = self.adb.execute_command(f'adb shell cat /proc/{pid}/stat')
            
            time.sleep(0.1)
            
            cpu_after = self.adb.execute_command('adb shell cat /proc/stat')
            proc_after = self.adb.execute_command(f'adb shell cat /proc/{pid}/stat')

            return self._calculate_cpu_usage(cpu_before, cpu_after, proc_before, proc_after)
        except Exception as e:
            logger.error(f"CPU 측정 실패: {e}")
            return 0.0

    def _get_memory(self) -> float:
        """메모리 사용량 측정"""
        try:
            result = self.adb.execute_command(
                f'adb shell dumpsys meminfo {self.selected_app}'
            )
            return self._parse_memory(result)
        except Exception as e:
            logger.error(f"메모리 측정 실패: {e}")
            return 0.0

    def _parse_fps(self, data: str) -> float:
        """FPS 데이터 파싱"""
        try:
            refresh_rate = 60.0  # 기본값
            
            # 주사율 확인
            for line in data.split('\n'):
                if 'fps' in line.lower():
                    try:
                        numbers = [float(s) for s in line.split() if s.replace('.', '').isdigit()]
                        if numbers and numbers[0] > 0:
                            refresh_rate = numbers[0]
                            break
                    except:
                        continue

            # 프레임 데이터 파싱
            vsync_missed = 0
            total_frames = 0
            
            for line in data.split('\n'):
                if 'Number Missed Vsync:' in line:
                    vsync_missed = int(line.split(':')[1].strip())
                elif 'Total frames rendered:' in line:
                    total_frames = int(line.split(':')[1].strip())

            if total_frames > 0:
                effective_frames = total_frames - vsync_missed
                if vsync_missed == 0:
                    return refresh_rate
                else:
                    fps_ratio = effective_frames / total_frames
                    return round(refresh_rate * fps_ratio, 1)

            return refresh_rate
        except Exception as e:
            logger.error(f"FPS 파싱 실패: {e}")
            return 0.0

    def _calculate_cpu_usage(self, cpu_before: str, cpu_after: str, 
                           proc_before: str, proc_after: str) -> float:
        """CPU 사용량 계산"""
        try:
            # 전체 CPU 시간 계산
            cpu_before_parts = cpu_before.split()[1:8]
            cpu_after_parts = cpu_after.split()[1:8]
            
            before_total = sum(map(int, cpu_before_parts))
            after_total = sum(map(int, cpu_after_parts))
            
            # 프로세스 CPU 시간 계산
            proc_before_parts = proc_before.split()
            proc_after_parts = proc_after.split()
            
            proc_before_time = int(proc_before_parts[13]) + int(proc_before_parts[14])
            proc_after_time = int(proc_after_parts[13]) + int(proc_after_parts[14])
            
            # CPU 사용률 계산
            cpu_delta = after_total - before_total
            proc_delta = proc_after_time - proc_before_time
            
            if cpu_delta > 0:
                cpu_usage = (proc_delta * 100.0) / cpu_delta
                return round(cpu_usage, 1)
                
            return 0.0
        except Exception as e:
            logger.error(f"CPU 사용량 계산 실패: {e}")
            return 0.0

    def _parse_memory(self, data: str) -> float:
        """메모리 사용량 파싱"""
        try:
            for line in data.split('\n'):
                if 'TOTAL' in line:
                    values = line.split()
                    if len(values) >= 2:
                        memory_kb = float(values[1])
                        memory_mb = memory_kb / 1024
                        return round(memory_mb, 2)
            return 0.0
        except Exception as e:
            logger.error(f"메모리 파싱 실패: {e}")
            return 0.0

    def _check_warnings(self, fps: float, cpu: float, memory: float):
        """성능 경고 확인"""
        if fps < config.FPS_WARNING_THRESHOLD:
            logger.warning(f"낮은 FPS 감지: {fps}")
        if cpu > config.CPU_WARNING_THRESHOLD:
            logger.warning(f"높은 CPU 사용량 감지: {cpu}%")
        if memory > config.MEMORY_WARNING_THRESHOLD:
            logger.warning(f"높은 메모리 사용량 감지: {memory}MB")