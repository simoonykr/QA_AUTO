# data_exporter.py
from datetime import datetime
import pandas as pd
from pathlib import Path
import matplotlib.pyplot as plt
from typing import Dict, Any
import os

from config import config
from exceptions import DataExportError
from logger import logger
from performance_monitor import PerformanceData

class DataExporter:
    def export_data(self, data: PerformanceData, app_name: str, fig: plt.Figure):
        """성능 데이터 내보내기"""
        try:
            # 저장 경로 생성
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            app_name_simple = app_name.split('.')[-1]
            base_filename = f"performance_{app_name_simple}_{timestamp}"
            
            # DataFrame 생성
            df = data.to_dataframe()
            if len(df) == 0:
                raise DataExportError("저장할 데이터가 없습니다.")
                
            # 통계 데이터 생성
            stats = pd.DataFrame({
                'Metric': ['FPS', 'CPU', 'Memory'],
                'Average': [
                    round(df['FPS'].mean(), 2),
                    round(df['CPU'].mean(), 2),
                    round(df['Memory'].mean(), 2)
                ],
                'Min': [
                    round(df['FPS'].min(), 2),
                    round(df['CPU'].min(), 2),
                    round(df['Memory'].min(), 2)
                ],
                'Max': [
                    round(df['FPS'].max(), 2),
                    round(df['CPU'].max(), 2),
                    round(df['Memory'].max(), 2)
                ]
            })
            
            # 저장 디렉토리 확인 및 생성
            save_dir = config.SAVE_DIR
            if not os.path.exists(save_dir):
                os.makedirs(save_dir)
            
            # Excel 파일 저장
            excel_path = os.path.join(save_dir, f"{base_filename}.xlsx")
            with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Raw Data', index=False)
                stats.to_excel(writer, sheet_name='Statistics', index=False)
                
                # 워크시트 설정
                workbook = writer.book
                raw_sheet = writer.sheets['Raw Data']
                stats_sheet = writer.sheets['Statistics']
                
                # 열 너비 자동 조정
                for sheet in [raw_sheet, stats_sheet]:
                    for column in sheet.columns:
                        max_length = 0
                        column = list(column)
                        for cell in column:
                            try:
                                if len(str(cell.value)) > max_length:
                                    max_length = len(cell.value)
                            except:
                                pass
                        adjusted_width = (max_length + 2)
                        sheet.column_dimensions[cell.column_letter].width = adjusted_width
            
            # 그래프 이미지 저장
            plot_path = os.path.join(save_dir, f"{base_filename}_graphs.png")
            fig.savefig(plot_path, dpi=300, bbox_inches='tight')
            
            # 상세 로그 저장
            log_path = os.path.join(save_dir, f"{base_filename}_details.txt")
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write("=== Performance Test Log ===\n")
                f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"App: {app_name}\n\n")
                
                f.write("=== Performance Statistics ===\n")
                f.write(stats.to_string())
                f.write("\n\n")
                
                f.write("=== Test Summary ===\n")
                f.write(f"Total Duration: {len(df)} seconds\n")
                f.write(f"FPS Drops: {len(df[df['FPS'] < config.FPS_WARNING_THRESHOLD])}\n")
                f.write(f"High CPU Usage: {len(df[df['CPU'] > config.CPU_WARNING_THRESHOLD])} seconds\n")
                f.write(f"High Memory Usage: {len(df[df['Memory'] > config.MEMORY_WARNING_THRESHOLD])} seconds\n")
            
            logger.info(f"데이터 저장 완료: {base_filename}")
            return True
            
        except Exception as e:
            logger.error(f"데이터 내보내기 실패: {e}")
            raise DataExportError(f"데이터 내보내기 실패: {e}")
            return False