import colorlog

def setup_logger(name: str | None = None):
    """로거 설정"""
    name = name or __name__
    handler = colorlog.StreamHandler()
    handler.setFormatter(colorlog.ColoredFormatter(
        fmt='%(asctime)s %(log_color)s[%(levelname)s]%(reset)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        log_colors={
            'DEBUG': 'bg_cyan',
            'INFO': 'bg_green',
            'WARNING': 'bg_yellow',
            'ERROR': 'bg_red',
            'CRITICAL': 'bg_purple',
        }
    ))
    
    logger = colorlog.getLogger(name)
    logger.addHandler(handler)
    logger.propagate = False
    
    return logger

logger = setup_logger()
