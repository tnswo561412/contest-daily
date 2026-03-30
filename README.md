# Contest Daily Update

공모전 정보를 스크래핑해 매일 자동으로 갱신하고, GitHub Pages로 공개하는 과제용 프로젝트입니다.

## 구성
- `scrape.py`: 콘테스트코리아 공모전 목록 스크래핑 + `contests.json`, `index.html` 생성
- `contests.json`: 수집 데이터
- `index.html`: 공개 웹페이지
- `.github/workflows/update.yml`: GitHub Actions 자동 갱신

## 로컬 실행
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scrape.py
```

실행 후 `index.html`을 브라우저에서 열면 결과를 볼 수 있습니다.

## GitHub Pages 배포
1. 이 폴더를 새 GitHub 저장소에 업로드
2. GitHub 저장소에서 **Settings → Pages** 이동
3. **Deploy from a branch** 선택
4. Branch를 `main`, 폴더를 `/root`로 설정 후 저장
5. 몇 분 뒤 공개 URL 생성

## 자동 업데이트
- `.github/workflows/update.yml`이 매일 오전 9시(KST 기준 자정 UTC)와 수동 실행에서 동작합니다.
- 스크래핑 결과가 바뀌면 자동으로 커밋합니다.

## 발표용 설명 문장
> Python으로 공모전 정보를 스크래핑하고, GitHub Actions를 이용해 매일 자동으로 갱신했습니다. 갱신된 결과는 GitHub Pages에 배포하여 누구나 접근 가능한 공개 웹페이지 형태로 제공했습니다.
