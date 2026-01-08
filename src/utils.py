from pathlib import Path

def sanitize_filename(name: str) -> str:
    """파일명에 사용할 수 없는 문자 제거"""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        name = name.replace(char, '_')
    return name.strip()

def cleanup_lockfiles(base_path: str) -> int:
    """기존 lockfile 정리"""
    try:
        recordings_path = Path(base_path).expanduser()
        
        if not recordings_path.exists():
            return 0
        
        lock_files = list(recordings_path.rglob('*.lock'))
        for lock_file in lock_files:
            lock_file.unlink(missing_ok=True)
        
        return len(lock_files)
    except Exception:
        return 0
