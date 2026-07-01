# Confluence Daily Uploader

회사 Confluence에 데일리 캡처/녹화 파일과 코멘트를 자동으로 올리는 Windows 트레이 앱입니다.

## 기능

- 회사 SSO 로그인창을 앱 안에서 띄웁니다.
- 로그인 후 저장한 브라우저 세션으로 Confluence REST API를 호출합니다.
- 로그인 브라우저 프로필을 로컬에 유지하고, 세션을 자동 저장하며, 실행 중 주기적으로 세션 유지 요청을 보냅니다.
- 설정된 상위 페이지 아래에 월별 데일리 페이지를 생성하거나 갱신합니다.
- 주차별 접힘 섹션과 `날짜 | 업무 내용 | 참고` 표를 만듭니다.
- 이미지/영상 파일을 Confluence 첨부로 업로드합니다.
- 파일 선택 대신 클립보드에 복사된 이미지를 바로 추가할 수 있습니다.
- 데일리 작성창에 파일을 드래그 앤 드랍하거나 `Ctrl+V`로 클립보드 파일/이미지를 붙여넣을 수 있습니다.
- 이미지는 미리보기로, 영상은 첨부 링크로 표에 넣습니다.
- 평일 지정 시각에 데일리 작성 알림을 띄웁니다.

## 실행

더블클릭:

```text
run_daily_uploader.bat
```

직접 실행:

```powershell
.\.venv\Scripts\python.exe -m confluence_daily
```

## 설정

처음 실행하면 `설정`에서 아래 값을 입력합니다.

- API 모드: 보통 사내 Confluence Server/Data Center는 `data_center`
- Confluence URL: 예시 `https://confluence.example.com`
- 로그인 계정 키: 세션 저장에 사용할 구분값
- Space ID / key: URL의 `/spaces/{SPACE_KEY}` 부분
- 상위 페이지 ID: URL의 `/pages/{PAGE_ID}` 숫자
- 페이지 이름: 월별 데일리 페이지 제목 앞부분
- 월 페이지 기준: `월~금 주차가 끝나는 월 페이지` 또는 `선택한 날짜의 월 페이지`
- 화면 테마: PC별 시스템 테마 차이를 피하려면 `라이트 모드` 또는 `다크 모드`를 명시적으로 선택

## 로그인 흐름

1. 앱을 실행합니다.
2. 저장된 Confluence 세션이 없으면 로그인창이 자동으로 열립니다.
3. 회사 SSO로 로그인합니다.
4. Confluence 페이지가 열리면 앱이 세션을 자동 저장합니다.
5. 이후 업로드는 저장된 브라우저 세션으로 처리됩니다.
6. 세션이 만료되면 앱이 다시 로그인창을 띄웁니다.

필요하면 로그인창의 `세션 저장` 버튼으로 수동 저장도 할 수 있습니다.
설정 창에서도 `로그인`, `세션 테스트`를 실행할 수 있습니다.

## 월 페이지 기준

설정의 `월 페이지 기준`에서 데일리를 어느 월 페이지에 올릴지 정합니다.

- `월~금 주차가 끝나는 월 페이지`: 2026년 6월 29일~30일도 2026년 7월 1주차로 올립니다.
- `선택한 날짜의 월 페이지`: 2026년 6월 29일은 2026년 6월 페이지로 올립니다.

## 클립보드 이미지

데일리 작성 창에서 `클립보드 이미지 추가`를 누르면 현재 클립보드에 복사된 이미지를 PNG로 저장하고 업로드 목록에 추가합니다. 추가된 이미지는 작성창의 이미지 프리뷰 영역에 바로 표시됩니다.
파일을 복사한 뒤 데일리 작성창에서 `Ctrl+V`를 누르면 해당 파일도 업로드 목록에 추가됩니다.

## 테스트

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

## 패키징

더블클릭:

```text
build_exe.bat
```

직접 실행:

```powershell
.\scripts\build_exe.ps1
```

버전을 지정해서 빌드:

```powershell
.\scripts\build_exe.ps1 -Version 0.1.1
```

빌드 결과는 `dist\ConfluenceDailyUploader\ConfluenceDailyUploader.exe`에 생성되고, 업데이트용 manifest는 `dist\latest.json`에 생성됩니다.
QtWebEngine 로그인창에 필요한 DLL과 리소스가 함께 들어가므로, 배포하거나 NAS 업데이트 경로에 올릴 때는 `dist\ConfluenceDailyUploader` 폴더 전체와 `dist\latest.json`을 함께 사용하세요.

이미 의존성을 설치한 뒤 빌드만 다시 할 때는 아래처럼 실행할 수 있습니다.

```powershell
.\scripts\build_exe.ps1 -SkipInstall
```

빌드 후 파일 서버 업데이트 경로에 바로 올릴 때는 아래처럼 실행합니다.

```powershell
.\scripts\build_exe.ps1 -Version 0.1.1 -PublishPath "\\server\share\Tools\ConfluenceDailyUploader"
```

## 업데이트 배포

NAS 또는 파일 서버의 업데이트 경로에는 아래 구조로 파일을 올립니다.

```text
Tools\ConfluenceDailyUploader\
  latest.json
  ConfluenceDailyUploader\
    ConfluenceDailyUploader.exe
    _internal\
    ...
```

`latest.json` 예시:

```json
{
  "version": "0.1.1",
  "folder": "ConfluenceDailyUploader",
  "notes": "변경 내용 메모"
}
```

앱 설정의 `업데이트 경로`에는 `latest.json`이 들어 있는 폴더를 지정합니다. 앱은 시작 시 이 manifest를 확인하고, 더 높은 버전이 있으면 업데이트 설치 여부를 묻습니다.
