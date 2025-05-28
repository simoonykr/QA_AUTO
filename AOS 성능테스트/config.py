# config.py
import os
from dataclasses import dataclass
from pathlib import Path

@dataclass
class Config:
    # ADB 설정
    ADB_PATH: str = r"C:\Users\nGle-simoony2\AppData\Local\Android\Sdk\platform-tools\adb.exe"
    
    # 성능 모니터링 설정
    MONITORING_INTERVAL: float = 1.0  # 초
    SCREENSHOT_INTERVAL: float = 1.0  # 초
    MAX_DATA_POINTS: int = 30
    
    # 그래프 설정
    GRAPH_UPDATE_INTERVAL: float = 1.0  # 초
    GRAPH_MIN_Y: float = 0.0
    GRAPH_MAX_FPS: float = 120.0
    GRAPH_MAX_CPU: float = 100.0
    GRAPH_MAX_MEMORY: float = 4096.0  # 4GB
    
    # 파일 저장 설정
    SAVE_DIR: Path = Path(r"C:\QA_AUTO\aos_performance\performance_logs")
    LOG_FILE: Path = Path(r"C:\QA_AUTO\aos_performance\performance_logs\app.log")
    
    # UI 설정
    WINDOW_TITLE: str = "모바일 게임 벤치마크"
    WINDOW_SIZE: tuple = (1200, 800)
    
    # 성능 임계값 설정
    CPU_WARNING_THRESHOLD: float = 90.0  # % (상향 조정)
    MEMORY_WARNING_THRESHOLD: float = 2048.0  # MB (2GB로 상향)
    FPS_WARNING_THRESHOLD: float = 30.0  # fps
    
    def __post_init__(self):
        # 저장 디렉토리 생성
        self.SAVE_DIR.mkdir(parents=True, exist_ok=True)
        # 로그 파일 디렉토리 생성
        self.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

config = Config()