# 컷레이더 · CUT RADAR

연출과 움직임을 찾는 애니메이션 레퍼런스. 시네마틱·애니메이션 제작에 쓸 카메라 워크, 액션, 감정 연기, FX 레퍼런스를 16축 필터와 키워드로 검색하는 정적 웹 도구입니다.

- 사이트: https://okometsbu-beep.github.io/CutRadar/
- 규칙: [GEMINI.md](GEMINI.md)

## 구조

```
index.html                  앱 뼈대(마크업) + 데이터 로더
style.css                   다크 테마·레이아웃
app.js                      검색·필터·YouTube 미리보기·타임라인 로직
data/index.json             메타데이터, 작품 목록, 청크 목록
data/videos_by_game/*.json  작품별 카탈로그 (파일당 4 MB 이하, 넘으면 -01, -02 로 분할)
scripts/split_cutradar.py   원본 단일 HTML → 위 구조로 분할·검증
```

`index.html`은 `data/index.json`과 작품별 JSON을 읽어 원래의 `window.SCENE_CATALOGUE`를 복원한 뒤 `app.js`를 실행합니다. 그래서 로컬에서 열 때는 파일 직접 열기가 아니라 정적 서버로 열어야 합니다.

```bash
python3 -m http.server 8000   # 저장소 루트에서 실행 후 http://localhost:8000
```

## 데이터 갱신

원본 `CutRadar_Standalone.html`을 새로 받았다면 저장소 루트에서:

```bash
python3 scripts/split_cutradar.py CutRadar_Standalone.html --out .
python3 scripts/split_cutradar.py --check .
```

분할은 공개용이므로 `durationEvidence`의 로컬 파일명·경로·FFprobe 로그를 지웁니다(`--keep-local`로 끌 수 있음). 원본 HTML은 저장소에 커밋하지 않습니다.

## Gemini 자동화

이슈 댓글에 `@gemini-cli`와 요청을 적으면 `.github/workflows/gemini-assistant.yml`이 Gemini CLI를 실행해 답변하거나 작업 브랜치와 PR을 만듭니다. 저장소 시크릿 `GEMINI_API_KEY`가 필요합니다.

쓰는 모델은 `.gemini/settings.json`에서 정합니다(현재 `gemini-3.8-flash`). 기본 Pro 프리뷰 모델은 혼잡 시 503(high demand)으로 재시도만 반복하므로 고정했습니다.

API 키는 결제 계정이 연결된 **Tier 1**(유료 등급, 선불 충전·자동 충전 OFF)으로 동작합니다. 무료 등급의 모델별 일일 한도(`gemini-3.8-flash` 20회/일 등)에 걸리지 않으므로 실제 개발 루프에 쓸 수 있습니다. 정확한 잔액·한도는 Google AI Studio의 결제 화면에서 확인합니다.
