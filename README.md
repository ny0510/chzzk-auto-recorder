# Chzzk auto recorder

## 설정

### 1. 쿠키 얻기

브라우저 개발자 도구(F12) → Application → Cookies → `https://chzzk.naver.com`에서 `NID_AUT`, `NID_SES` 복사

### 2. 채널 ID 찾기

`https://chzzk.naver.com/live/{channel_id}` URL에서 채널 ID 확인

### 3. 설정 파일 작성

```bash
cp config/config.example.yaml config.yaml
```

파일 복사 후 설명에 따라 `config.yaml` 파일 수정

### 4. 실행

```bash
docker compose up -d
```
