# ffmpeg 설치 가이드

Tag Database는 동영상 파일(WebM, MP4 등)의 썸네일 생성에 ffmpeg를 사용합니다.

## Windows

### 옵션 1: Scoop (권장)
```powershell
# Scoop 설치 (미설치 시)
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
irm get.scoop.sh | iex

# ffmpeg 설치
scoop install ffmpeg
```

### 옵션 2: Chocolatey
```powershell
# Chocolatey 설치 (미설치 시)
# 관리자 권한으로 실행
Set-ExecutionPolicy Bypass -Scope Process -Force
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

# ffmpeg 설치
choco install ffmpeg
```

### 옵션 3: 수동 다운로드
1. 다운로드: https://www.gyan.dev/ffmpeg/builds/
2. `C:\ffmpeg`에 압축 해제
3. PATH에 추가:
   - "환경 변수" 열기
   - "Path" 편집
   - `C:\ffmpeg\bin` 추가
4. 터미널 재시작

---

## macOS

### Homebrew (권장)
```bash
# Homebrew 설치 (미설치 시)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# ffmpeg 설치
brew install ffmpeg
```

---

## Linux

### Ubuntu/Debian
```bash
sudo apt update
sudo apt install ffmpeg
```

### Fedora
```bash
sudo dnf install ffmpeg
```

### Arch
```bash
sudo pacman -S ffmpeg
```

---

## 설치 확인

```bash
ffmpeg -version
```

버전 정보가 출력되어야 합니다.

---

## 동영상 썸네일 테스트

```bash
# WebUI 시작
python web_ui.py --db tags.db

# WebM 파일로 이동
# 썸네일이 자동으로 생성됩니다
```

---

## 문제 해결

### "ffmpeg not installed" 오류

**증상**: 동영상 썸네일에 오류 메시지가 표시됨

**해결 방법**:
1. ffmpeg 설치 확인: `ffmpeg -version`
2. 터미널/PowerShell 재시작
3. WebUI 재시작
4. PATH 설정 확인

### 썸네일이 생성되지 않음

**증상**: 썸네일에 "Failed to extract video frame" 표시

**가능한 원인**:
- 동영상 파일 손상
- 지원하지 않는 동영상 코덱
- ffmpeg 타임아웃 (10초 초과)

**디버그**:
```bash
# 수동 테스트
ffmpeg -i your_video.webm -ss 00:00:01 -vframes 1 test_thumb.jpg

# 로그 확인
# "[ERROR] ffmpeg" 메시지 찾기
```

---

## 선택사항: GPU 가속

더 빠른 동영상 처리를 위해 (고급):

### Windows (NVIDIA)
```bash
# NVIDIA 빌드 다운로드:
# https://www.gyan.dev/ffmpeg/builds/
# "ffmpeg-release-full.7z" 선택
```

### macOS (VideoToolbox)
```bash
# Homebrew 빌드에 이미 포함되어 있음
```

### Linux (VAAPI)
```bash
sudo apt install ffmpeg vainfo
```

---

## 성능 참고사항

- 최초 썸네일 생성: 약 1-3초
- 캐시된 썸네일: 100ms 미만
- ZIP 파일: 임시 디렉토리에 압축 해제 후 처리
- 타임아웃: 동영상당 10초

---

## ffmpeg 없이 사용

ffmpeg를 사용할 수 없는 경우:
- 동영상 파일 썸네일에 오류가 표시됩니다
- 메타데이터로 동영상 검색은 가능합니다
- 완전한 기능을 위해 ffmpeg 설치를 권장합니다
