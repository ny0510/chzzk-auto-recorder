
import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

import aiohttp
import colorlog
import yaml

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

logger = colorlog.getLogger(__name__)
logger.addHandler(handler)
logger.propagate = False

class ChzzkRecorder:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.cookies = config['cookies']
        self.channels = config['channels']
        self.output_config = config['output']
        self.monitoring_config = config['monitoring']
        self.session: Optional[aiohttp.ClientSession] = None
        self.channel_names: Dict[str, str] = {}  # channel_id -> channel_name 매핑
        self.active_locks: set[Path] = set()  # 활성 lockfile 추적
        
    async def start(self):
        logger.info(f"치지직 자동 녹화를 시작합니다.")
        
        headers = { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36' }
        self.session = aiohttp.ClientSession(headers=headers)
        
        try:
            # 기존 lockfile 정리
            self.cleanup_old_lockfiles()
            
            # 채널 검증
            await self.validate_channels()
            
            # 각 채널마다 독립적인 모니터링 태스크 생성
            tasks = [
                asyncio.create_task(self.monitor_channel(channel_id))
                for channel_id in self.channels
            ]
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.critical(f"오류가 발생하여 프로그램을 종료합니다: {e}")
        finally:
            # 모든 lockfile 정리
            self.cleanup_all_lockfiles()
            await self.session.close()
    
    async def validate_channels(self):
        logger.debug("채널 검증 중...")
        invalid_channels = []
        
        if self.session is None:
            logger.error("HTTP 세션이 초기화되지 않았습니다")
            return
        
        for channel_id in self.channels:
            url = f"https://api.chzzk.naver.com/service/v1/channels/{channel_id}"
            try:
                async with self.session.get(url) as response:
                    if response.status == 404:
                        invalid_channels.append(channel_id)
                    elif response.status != 200:
                        logger.warning(f"[{channel_id}] API 응답 오류 (HTTP {response.status})")
                    else:
                        data = await response.json()
                        channel_name = data.get('content', {}).get('channelName', channel_id)
                        self.channel_names[channel_id] = channel_name
                        logger.debug(f"{channel_name} ({channel_id}) 검증 성공")
            except Exception as e:
                logger.error(f"[{channel_id}] 검증 실패: {e}")
                invalid_channels.append(channel_id)
        
        if invalid_channels:
            logger.error(f"잘못된 채널 ID: {', '.join(invalid_channels)}")
            raise ValueError(f"{len(invalid_channels)}개의 잘못된 채널 ID가 발견되었습니다")
        
        channel_names_list = ', '.join([self.channel_names[ch_id] for ch_id in self.channels])
        logger.info(f"모니터링 채널 ({len(self.channels)}개): [{channel_names_list}]")
        logger.debug("모든 채널 검증 완료")
    
    def cleanup_old_lockfiles(self):
        """시작 시 기존 lockfile 정리"""
        logger.debug("lockfile 정리 시작...")
        try:
            # './recordings/{author}/' -> './recordings'
            base_path = self.output_config['path'].split('{')[0].rstrip('/')
            recordings_path = Path(base_path).expanduser()
            
            logger.debug(f"lockfile 검색 경로: {recordings_path.absolute()}")
            
            if not recordings_path.exists():
                logger.debug(f"녹화 디렉토리가 존재하지 않습니다: {recordings_path}")
                return
            
            lock_count = 0
            lock_files = list(recordings_path.rglob('*.lock'))
            logger.debug(f"발견된 lockfile: {len(lock_files)}개")
            
            for lock_file in lock_files:
                try:
                    lock_file.unlink()
                    lock_count += 1
                    logger.debug(f"lockfile 삭제: {lock_file}")
                except Exception as e:
                    logger.warning(f"lockfile 삭제 실패: {lock_file.name} - {e}")
            
            if lock_count > 0:
                logger.info(f"기존 lockfile {lock_count}개 정리 완료")
            else:
                logger.debug("삭제할 lockfile이 없습니다")
        except Exception as e:
            logger.warning(f"lockfile 정리 중 오류: {e}")
    
    def cleanup_all_lockfiles(self):
        """종료 시 모든 활성 lockfile 삭제"""
        if not self.active_locks:
            return
        
        logger.info(f"lockfile 정리 중... ({len(self.active_locks)}개)")
        for lock_file in list(self.active_locks):
            try:
                if lock_file.exists():
                    lock_file.unlink()
                    logger.debug(f"lockfile 삭제: {lock_file.name}")
            except Exception as e:
                logger.warning(f"lockfile 삭제 실패: {lock_file.name} - {e}")
        self.active_locks.clear()
    
    async def monitor_channel(self, channel_id: str):
        channel_name = self.channel_names.get(channel_id, channel_id)
        logger.info(f"[{channel_name}] 모니터링 시작")
        
        while True:
            try:
                # 방송 상태 확인
                live_info = await self.check_live_status(channel_id)
                channel_name = self.channel_names.get(channel_id, channel_id)
                logger.debug(f"[{channel_name}] 방송 상태: {live_info}")
                
                if live_info and live_info['status'] == 'OPEN':
                    # 방송 중이면 녹화 시작
                    await self.start_recording(channel_id, live_info)
                
                # 다음 체크까지 대기
                await asyncio.sleep(self.monitoring_config['check_interval'])
                
            except Exception as e:
                channel_name = self.channel_names.get(channel_id, channel_id)
                logger.error(f"[{channel_name}] 모니터링 오류: {e}")
                await asyncio.sleep(self.monitoring_config['check_interval'])
    
    async def check_live_status(self, channel_id: str) -> Optional[Dict[str, Any]]:
        url = f"https://api.chzzk.naver.com/service/v3/channels/{channel_id}/live-detail"
        
        if self.session is None:
            return None
        
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    content = data.get('content', {})
                    
                    # openDate 파싱 (형식: "2026-01-05 20:01:25")
                    open_date_str = content.get('openDate')
                    open_date = None
                    if open_date_str:
                        try:
                            open_date = datetime.strptime(open_date_str, '%Y-%m-%d %H:%M:%S')
                        except ValueError:
                            logger.debug(f"[{channel_id}] openDate 파싱 실패: {open_date_str}")
                    
                    return {
                        'status': content.get('status'),
                        'liveTitle': content.get('liveTitle', 'Unknown'),
                        'channelName': content.get('channel', {}).get('channelName', 'Unknown'),
                        'liveId': content.get('liveId'),
                        'openDate': open_date,
                    }
        except Exception as e:
            logger.debug(f"[{channel_id}] API 요청 실패: {e}")
        
        return None
    
    async def start_recording(self, channel_id: str, live_info: Dict[str, Any]):
        channel_name = live_info['channelName']
        title = live_info['liveTitle']
        live_id = live_info['liveId']
        open_date = live_info.get('openDate') or datetime.now()
        
        # 출력 경로 및 파일
        output_path, output_file = self.prepare_output_path(
            channel_name, title, open_date
        )
        
        # 중복 녹화 방지
        lock_file = output_path / f"{output_file}.lock"
        if lock_file.exists():
            logger.info(f"[{channel_name}] 녹화 건너뜀: 이미 녹화 중인 방송입니다.")
            return
        
        try:
            # lock 파일 생성
            lock_file.touch()
            self.active_locks.add(lock_file)
            logger.info(f"[{channel_name}] 방송 시작 감지: {title}")
            
            temp_file = output_path / f"temp_{output_file}"
            final_file = output_path / output_file
            
            # 기존 temp 파일이 있으면 삭제
            if temp_file.exists():
                logger.warning(f"[{channel_name}] 기존 temp 파일 삭제: {temp_file.name}")
                temp_file.unlink()
            
            # streamlink 명령어 구성
            streamlink_cmd = self.build_streamlink_command(
                channel_id, str(temp_file)
            )
            
            # 녹화 시작
            logger.info(f"[{channel_name}] 녹화 시작: {final_file}")
            process = await asyncio.create_subprocess_exec(
                *streamlink_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # stderr 로그 출력 태스크
            async def log_stderr():
                if process.stderr:
                    async for line in process.stderr:
                        line_str = line.decode('utf-8', errors='ignore').strip()
                        if line_str:
                            logger.debug(f"[{channel_name}] streamlink: {line_str}")
            
            stderr_task = asyncio.create_task(log_stderr())
            
            # 방송 종료 감지 및 프로세스 종료 대기
            await self.wait_for_stream_end(
                channel_id, live_id, process, channel_name
            )
            
            # streamlink 프로세스 정상 종료 확인
            await process.wait()
            await stderr_task
            
            if process.returncode != 0:
                logger.error(f"[{channel_name}] streamlink 오류 종료 (exit code: {process.returncode})")
            
            logger.info(f"[{channel_name}] 녹화 완료")
            
            # ffmpeg로 타임스탬프 재설정
            if temp_file.exists():
                await self.fix_timestamps(temp_file, final_file, channel_name)
                temp_file.unlink()  # 임시 파일 삭제
            
        except Exception as e:
            logger.error(f"[{channel_name}] 녹화 오류: {e}")
        finally:
            # lock 파일 삭제
            if lock_file in self.active_locks:
                self.active_locks.remove(lock_file)
            if lock_file.exists():
                lock_file.unlink()
    
    def prepare_output_path(self, author: str, title: str, stream_start_time: datetime) -> tuple[Path, str]:
        # 경로 템플릿 처리 (author, title, time)
        path_template = self.output_config['path']
        path_str = path_template.format(
            author=self.sanitize_filename(author),
            title=self.sanitize_filename(title),
            time=stream_start_time
        )
        output_path = Path(path_str).expanduser()
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 파일명 템플릿 처리 (author, title, time)
        filename_template = self.output_config['filename']
        filename = filename_template.format(
            author=self.sanitize_filename(author),
            title=self.sanitize_filename(title),
            time=stream_start_time
        )
        
        return output_path, filename
    
    @staticmethod
    def sanitize_filename(name: str) -> str:
        """파일명에 사용할 수 없는 문자 제거"""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, '_')
        return name.strip()
    
    def build_streamlink_command(self, channel_id: str, output_file: str) -> list[str]:
        url = f"https://chzzk.naver.com/live/{channel_id}"
        quality = self.output_config.get('quality', 'best')
        
        cmd = [
            'streamlink',
            '--output', output_file,
            '--progress', 'no',
            '--ffmpeg-start-at-zero',
            '--ffmpeg-copyts',
            '--http-cookie', f"NID_AUT={self.cookies['NID_AUT']}",
            '--http-cookie', f"NID_SES={self.cookies['NID_SES']}",
            url,
            quality
        ]
        
        return cmd
    
    async def wait_for_stream_end(
        self, channel_id: str, live_id: str, process: asyncio.subprocess.Process,
        channel_name: str
    ):
        check_interval = self.monitoring_config['stop_check_interval']
        
        # 첫 체크 전 대기
        await asyncio.sleep(check_interval)
        
        while True:
            # 프로세스가 이미 종료되었는지 확인
            if process.returncode is not None:
                logger.debug(f"[{channel_name}] streamlink 프로세스 종료 감지")
                break
            
            # API로 방송 상태 확인
            live_info = await self.check_live_status(channel_id)
            
            # 방송이 종료되었거나 다른 방송으로 변경됨
            if not live_info or live_info['status'] != 'OPEN' or live_info['liveId'] != live_id:
                logger.info(f"[{channel_name}] 방송 종료 감지")
                try:
                    process.terminate()
                    await asyncio.sleep(5)
                    if process.returncode is None:
                        process.kill()
                except:
                    pass
                break
            
            await asyncio.sleep(check_interval)
    
    async def fix_timestamps(self, temp_file: Path, final_file: Path, channel_name: str):
        logger.info(f"[{channel_name}] 타임스탬프 재설정 중...")
        
        cmd = [
            'ffmpeg',
            '-i', str(temp_file),
            '-c', 'copy',
            '-map', '0',
            '-reset_timestamps', '1',
            '-y',  # 덮어쓰기
            str(final_file)
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        
        await process.wait()
        
        if process.returncode == 0:
            logger.info(f"[{channel_name}] 후처리 완료: {final_file}")
        else:
            logger.error(f"[{channel_name}] 후처리 실패 (원본 파일 유지됨)")
            # 실패 시 임시 파일을 최종 파일로 이동
            temp_file.rename(final_file)

def load_config(config_path: str = 'config.yaml') -> Dict[str, Any]:
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 필수 항목 검증
        required_keys = ['cookies', 'channels', 'output', 'monitoring']
        for key in required_keys:
            if key not in config:
                raise ValueError('설정 파일이 올바르지 않습니다: 누락된 항목 - ' + key)
        
        return config
    except FileNotFoundError:
        logger.error(f"설정 파일을 찾을 수 없습니다: {config_path}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"설정 파일 로드 실패: {e}")
        sys.exit(1)


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

