import asyncio
import sys

import colorlog

from src.config import load_config
from src.logger import logger
from src.recorder import ChzzkRecorder

async def main():
    config = load_config()
    
    log_level = config.get('logging', {}).get('level', 'INFO').upper() or 'INFO'
    level_map = {
        'DEBUG': colorlog.DEBUG,
        'INFO': colorlog.INFO,
        'WARNING': colorlog.WARNING,
        'ERROR': colorlog.ERROR,
        'CRITICAL': colorlog.CRITICAL,
    }
    logger.setLevel(level_map.get(log_level, colorlog.INFO))
    
    recorder = ChzzkRecorder(config)
    await recorder.start()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)

