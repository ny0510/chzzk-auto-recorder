import sys
from typing import Dict, Any

import yaml

from src.logger import logger

def load_config(config_path: str = 'config.yaml') -> Dict[str, Any]:
    """설정 파일 로드"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 필수 항목 검증
        required_keys = ['cookies', 'channels', 'output', 'monitoring']
        for key in required_keys:
            if key not in config:
                raise ValueError(f'설정 파일이 올바르지 않습니다: 누락된 항목 - {key}')
        
        return config
    except FileNotFoundError:
        logger.error(f"설정 파일을 찾을 수 없습니다: {config_path}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"설정 파일 로드 실패: {e}")
        sys.exit(1)
