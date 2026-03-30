# Contest Daily Update

공모전 정보를 스크래핑해 30분마다 자동으로 갱신하고, GitHub Pages로 공개하는 과제용 프로젝트입니다.

## 구성
- `scrape.py`: 콘테스트코리아 공모전 목록을 여러 페이지에서 수집하고 `contests.json`, `index.html` 생성
- `contests.json`: 수집 데이터 + 실행 시각 + 수집 조건 메타데이터
- `index.html`: 공개 웹페이지
- `.github/workflows/update.yml`: GitHub Actions 자동 갱신

## 현재 수집 조건
- 대상 사이트: ContestKorea 공개 공모전 목록 (`int_gbn=1`)
- 페이지당 수집 수: 12건
- 수집 페이지 수: 사이트 pagination에서 감지한 페이지 수 중 최대 5페이지
- 총 수집 한도: 최대 60건 시도
- 실제 페이지 파라미터: `page` (소문자)
- 정렬 우선순위: `접수중` → `접수예정` → 기타
- 중복 제거 기준: 상세 링크(`detail_url`)
- 동일한 목록 페이지가 반복 응답되면 추가 수집 중단

## 개선한 점
- ContestKorea 실제 페이지네이션 파라미터(`page`)를 따라 여러 페이지 순회하도록 수정
- 첫 페이지의 pagination 링크에서 사이트 전체 페이지 수를 감지하고, 그중 최대 5페이지만 수집하도록 보강
- 수집 조건과 상태별 개수를 `contests.json`에 함께 저장
- 웹페이지를 `접수중`, `접수예정`, `기타` 섹션으로 분리
- 페이지 설명 문구를 실제 30분 갱신 주기에 맞게 정리
- HTML 출력 시 문자열 이스케이프를 적용해 표시 안정성 개선

## 로컬 실행
### Windows PowerShell
```powershell
py scrape.py
```

### 일반 Python 환경
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scrape.py
```

실행 후 `index.html`을 브라우저에서 열면 결과를 볼 수 있습니다.

## GitHub Pages 배포
1. 이 폴더를 GitHub 저장소에 업로드
2. GitHub 저장소에서 **Settings → Pages** 이동
3. **Deploy from a branch** 선택
4. Branch를 `main`, 폴더를 `/root`로 설정 후 저장
5. 몇 분 뒤 공개 URL 생성

## 자동 업데이트
- `.github/workflows/update.yml`이 `*/30 * * * *` 크론으로 30분마다 실행됩니다.
- 실행 때마다 `scrape.py`가 최신 목록을 다시 수집합니다.
- `contests.json`, `index.html`에 변경이 있을 때만 자동 커밋합니다.
- 필요하면 GitHub Actions의 **Run workflow**로 수동 실행도 가능합니다.

## 발표용 설명 문장
> Python으로 공모전 정보를 스크래핑하고, GitHub Actions를 이용해 30분마다 자동 갱신되도록 구성했습니다. 최근 목록을 여러 페이지에서 수집한 뒤 상태별로 정리해 GitHub Pages로 배포했습니다.
