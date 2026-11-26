#!/usr/bin/env python3
"""CutRadar 단일 HTML을 GitHub Pages용 구조로 분할한다.

입력:  CutRadar_Standalone.html (스타일·카탈로그·앱 코드가 한 파일에 들어 있는 원본)
출력:  index.html, style.css, app.js, data/index.json, data/videos_by_game/*.json

구조와 규칙은 저장소 루트의 GEMINI.md 2·4절을 따른다.
  - 작품별 JSON은 파일 하나가 4 MB를 넘지 않게 parts로 나눈다.
  - 공개용 데이터에서는 durationEvidence의 로컬 파일명·경로·FFprobe 로그를 지운다(--strip-local, 기본값).

사용 예:
  python scripts/split_cutradar.py CutRadar_Standalone.html --out .
  python scripts/split_cutradar.py --check .
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

MAX_BYTES = 4 * 1024 * 1024  # GEMINI.md: 작품별 JSON 단일 파일 4 MB 이하

# 작품 이름 → 파일 슬러그. 새 작품은 자동 슬러그로 떨어지므로 필요할 때 여기에 추가한다.
KNOWN_SLUGS = {
    "붕괴3rd": "honkai-impact-3rd",
    "원신": "genshin-impact",
    "붕괴: 스타레일": "honkai-star-rail",
    "젠레스 존 제로": "zenless-zone-zero",
    "아케인": "arcane",
    "명조": "wuthering-waves",
    "리그 오브 레전드": "league-of-legends",
    "명일방주: 엔드필드": "arknights-endfield",
    "퍼니싱: 그레이 레이븐": "punishing-gray-raven",
    "명일방주": "arknights",
    "에픽세븐": "epic-seven",
    "그랑블루 판타지: 리링크": "granblue-fantasy-relink",
    "로스트아크": "lost-ark",
}

LOCAL_FILE_RE = re.compile(r"([\w.\-]+)\.(?:mkv|mp4|mov|avi|webm)\b", re.IGNORECASE)
FFPROBE_PATTERNS = [
    (re.compile(r"FFprobe format\.duration="), ""),
    (re.compile(r"FFprobe 기반 manifest duration="), "길이 "),
    (re.compile(r"FFprobe 기반 manifest\s*:\s*"), "길이 "),
    (re.compile(r"FFprobe 기반 manifest"), "길이 근거"),
    (re.compile(r"FFprobe\s+"), ""),
]
LOCAL_PATH_RE = re.compile(r"(?<![\w:/])/(?:Users|home|Volumes|mnt)/[^\s;,)]+")
WINDOWS_PATH_RE = re.compile(r"\b[A-Za-z]:\\\\?[^\s;,)]+")


def slug_for(game: str, index: int) -> str:
    if game in KNOWN_SLUGS:
        return KNOWN_SLUGS[game]
    slug = re.sub(r"[^a-z0-9]+", "-", game.lower()).strip("-")
    if slug:
        return slug
    return f"game-{index:02d}"


def strip_local_text(text: str) -> str:
    if not isinstance(text, str) or not text:
        return text
    out = LOCAL_PATH_RE.sub("", text)
    out = WINDOWS_PATH_RE.sub("", out)
    out = LOCAL_FILE_RE.sub(lambda m: m.group(1), out)  # 로컬 파일명의 확장자만 제거
    for pattern, repl in FFPROBE_PATTERNS:
        out = pattern.sub(repl, out)
    return re.sub(r"\s{2,}", " ", out).strip()


def strip_local(catalogue: dict) -> int:
    """공개용 데이터에서 로컬 원본 흔적을 지운다. 지운 항목 수를 돌려준다."""
    changed = 0
    for video in catalogue.get("videos", []):
        for field in ("durationEvidence",):
            before = video.get(field)
            after = strip_local_text(before)
            if after != before:
                video[field] = after
                changed += 1
        for key in ("localFile", "localPath", "filePath", "ffprobe"):
            if key in video:
                video.pop(key)
                changed += 1
    return changed


def extract(html: str) -> dict:
    style_open = html.index("<style>")
    style_close = html.index("</style>", style_open)
    data_at = html.index("window.SCENE_CATALOGUE=")
    data_script_open = html.rindex("<script", 0, data_at)
    data_script_close = html.index("</script>", data_at)
    scripts = [m for m in re.finditer(r"<script\b[^>]*>(.*?)</script>", html, re.S)]
    data_script = next(s for s in scripts if "window.SCENE_CATALOGUE=" in s.group(1))
    app_parts = [s.group(1) for s in scripts if s is not data_script]

    data_text = data_script.group(1)
    eq = data_text.index("window.SCENE_CATALOGUE=") + len("window.SCENE_CATALOGUE=")
    json_text = data_text[eq:].strip()
    if json_text.endswith(";"):
        json_text = json_text[:-1]
    catalogue = json.loads(json_text)

    return {
        "head": html[:style_open],
        "css": html[style_open + len("<style>") : style_close].strip("\n"),
        "markup": html[style_close + len("</style>") : data_script_open],
        "app_js": "\n".join(part.strip("\n") for part in app_parts).strip("\n"),
        "catalogue": catalogue,
    }


BOOTSTRAP = """<script>
/* CutRadar 데이터 로더: data/index.json과 작품별 JSON을 읽어 window.SCENE_CATALOGUE를
   복원한 뒤 app.js를 실행한다. 정적 호스팅(GitHub Pages)과 로컬 서버 모두에서 동작한다. */
(() => {
  'use strict';
  const status = (text, progressText) => {
    let el = document.getElementById('cutradarDataStatus');
    if (!el) {
      el = document.createElement('p');
      el.id = 'cutradarDataStatus';
      el.setAttribute('role', 'status');
      el.setAttribute('aria-live', 'polite');
      el.className = 'sr-only';
      document.body.appendChild(el);
    }
    el.textContent = text;
    const statsEl = document.getElementById('catalogueStats');
    if (statsEl) statsEl.textContent = text;
    if (progressText) {
      const invEl = document.getElementById('inventoryStatus');
      if (invEl) invEl.textContent = progressText;
    }
  };
  const fail = error => {
    const box = document.createElement('div');
    box.setAttribute('role', 'alert');
    box.style.cssText = 'margin:24px;padding:16px 18px;border:1px solid #54565a;border-radius:6px;background:#1e2023;color:#e4e3de;line-height:1.6;font-size:13px';
    box.innerHTML = '<strong>카탈로그 데이터를 불러오지 못했습니다.</strong><br>' +
      '이 페이지는 data/ 폴더의 JSON을 읽어 동작합니다. 로컬 파일을 직접 열었다면 저장소 루트에서 ' +
      '<code>python3 -m http.server</code> 같은 정적 서버로 열어 주세요.<br><span style="color:#96999f"></span>';
    box.lastElementChild.textContent = String(error && error.message || error);
    document.body.prepend(box);
    status('데이터 로딩 실패', '새로고침해 다시 시도해 주세요');
  };
  const getJSON = (path, cache) => fetch(path, { cache: cache }).then(response => {
    if (!response.ok) throw new Error(path.split('/').pop() + ' · HTTP ' + response.status);
    return response.json();
  });
  const load = async () => {
    const index = await getJSON('data/index.json', 'no-cache');
    const chunks = index.chunks || [];
    status('데이터 불러오는 중 0/' + chunks.length, '카탈로그 청크 수신 준비');
    const slots = new Array(index.videoCount || 0);
    let done = 0;
    const queue = chunks.slice();
    const worker = async () => {
      while (queue.length) {
        const chunk = queue.shift();
        const payload = await getJSON(chunk.path, 'no-cache');
        payload.videos.forEach((video, i) => { slots[payload.orders[i]] = video; });
        done += 1;
        status('데이터 불러오는 중 ' + done + '/' + chunks.length, Math.round((done / chunks.length) * 100) + '% 완료 · 잠시만 기다려 주세요');
      }
    };
    await Promise.all(Array.from({ length: Math.min(4, chunks.length) }, worker));
    const missing = slots.filter(video => !video).length;
    if (missing) throw new Error('누락된 영상 ' + missing + '건');
    const { chunks: _chunks, games: _games, generatedAt: _generatedAt, source: _source, ...meta } = index;
    window.SCENE_CATALOGUE = Object.assign({}, meta, { videos: slots });
    status('카탈로그 ' + slots.length + '편 준비 완료', '앱 실행 중…');
    await new Promise(resolve => {
      const script = document.createElement('script');
      script.src = 'app.js';
      script.onload = resolve;
      script.onerror = () => { fail(new Error('app.js를 불러오지 못했습니다.')); resolve(); };
      document.body.appendChild(script);
    });
  };
  load().catch(fail);
})();
</script>"""


def build_site(source: Path, out_dir: Path, strip: bool = True, max_bytes: int = MAX_BYTES) -> dict:
    html = source.read_text(encoding="utf-8")
    parts = extract(html)
    catalogue = parts["catalogue"]

    stripped = strip_local(catalogue) if strip else 0

    videos = catalogue["videos"]
    buckets: "OrderedDict[str, list[tuple[int, dict]]]" = OrderedDict()
    for order, video in enumerate(videos):
        buckets.setdefault(video.get("game") or "(미분류)", []).append((order, video))

    data_dir = out_dir / "data" / "videos_by_game"
    data_dir.mkdir(parents=True, exist_ok=True)
    for stale in data_dir.glob("*.json"):
        stale.unlink()

    games_meta, chunks_meta = [], []
    for index, (game, items) in enumerate(buckets.items(), start=1):
        slug = slug_for(game, index)
        # 4 MB 제한에 맞춰 작품 안에서 순서를 유지한 채 parts로 나눈다.
        page, page_bytes = [], 200  # {"game":..,"part":..,"parts":..,"orders":[..],"videos":[..]} 뼈대 여유분
        pages = []
        for order, video in items:
            size = len(json.dumps(video, ensure_ascii=False).encode("utf-8")) + len(str(order)) + 2
            if page and page_bytes + size > max_bytes:
                pages.append(page)
                page, page_bytes = [], 200
            page.append((order, video))
            page_bytes += size
        if page:
            pages.append(page)

        files = []
        for part_no, page in enumerate(pages, start=1):
            name = f"{slug}.json" if len(pages) == 1 else f"{slug}-{part_no:02d}.json"
            payload = {
                "game": game,
                "part": part_no,
                "parts": len(pages),
                "orders": [order for order, _ in page],
                "videos": [video for _, video in page],
            }
            path = data_dir / name
            path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            rel = f"data/videos_by_game/{name}"
            files.append(rel)
            chunks_meta.append({"path": rel, "game": game, "part": part_no, "videos": len(page), "bytes": path.stat().st_size})
        games_meta.append({"name": game, "slug": slug, "videos": len(items), "files": files})

    index_payload = {
        "schemaVersion": catalogue.get("schemaVersion", 1),
        "inventoryComplete": catalogue.get("inventoryComplete", False),
        "inventoryEvidence": catalogue.get("inventoryEvidence", ""),
        "summary": catalogue.get("summary", {}),
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": source.name,
        "videoCount": len(videos),
        "segmentCount": sum(len(v.get("segments") or []) for v in videos),
        "chunks": chunks_meta,
        "games": games_meta,
    }
    (out_dir / "data" / "index.json").write_text(
        json.dumps(index_payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    (out_dir / "style.css").write_text(parts["css"] + "\n", encoding="utf-8")
    (out_dir / "app.js").write_text(parts["app_js"] + "\n", encoding="utf-8")

    shell = (
        parts["head"]
        + '<link rel="stylesheet" href="style.css">'
        + parts["markup"]
        + BOOTSTRAP
        + "\n</body></html>\n"
    )
    (out_dir / "index.html").write_text(shell, encoding="utf-8")

    return {
        "videos": len(videos),
        "segments": index_payload["segmentCount"],
        "games": len(games_meta),
        "chunks": len(chunks_meta),
        "stripped": stripped,
        "index_bytes": (out_dir / "data" / "index.json").stat().st_size,
        "app_bytes": (out_dir / "app.js").stat().st_size,
    }


def check(root: Path, max_bytes: int = MAX_BYTES) -> list[str]:
    problems: list[str] = []
    for name in ("index.html", "style.css", "app.js", "data/index.json"):
        if not (root / name).exists():
            problems.append(f"누락: {name}")
    if problems:
        return problems
    index = json.loads((root / "data" / "index.json").read_text(encoding="utf-8"))
    orders: set[int] = set()
    total = 0
    for chunk in index.get("chunks", []):
        path = root / chunk["path"]
        if not path.exists():
            problems.append(f"누락: {chunk['path']}")
            continue
        size = path.stat().st_size
        if size > max_bytes:
            problems.append(f"4 MB 초과: {chunk['path']} ({size / 1024 / 1024:.2f} MB)")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if len(payload.get("orders", [])) != len(payload.get("videos", [])):
            problems.append(f"orders/videos 길이 불일치: {chunk['path']}")
        for order in payload.get("orders", []):
            if order in orders:
                problems.append(f"중복 순번 {order} in {chunk['path']}")
            orders.add(order)
        total += len(payload.get("videos", []))
        for video in payload.get("videos", []):
            for field in ("id", "title", "officialUrl", "segments"):
                if field not in video:
                    problems.append(f"schema 누락 {field}: {chunk['path']}")
                    break
            evidence = video.get("durationEvidence") or ""
            if LOCAL_FILE_RE.search(evidence) or "FFprobe" in evidence:
                problems.append(f"로컬 흔적 잔존: {video.get('id')} · {evidence[:60]}")
    if total != index.get("videoCount"):
        problems.append(f"영상 수 불일치: index {index.get('videoCount')} vs 파일 {total}")
    if len(orders) != total:
        problems.append("순번 누락 또는 중복")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="CutRadar 단일 HTML을 정적 사이트 구조로 분할한다.")
    parser.add_argument("source", nargs="?", help="CutRadar_Standalone.html 경로")
    parser.add_argument("--out", default=".", help="출력 디렉터리 (기본: 현재 디렉터리)")
    parser.add_argument("--keep-local", action="store_true", help="durationEvidence의 로컬 흔적을 지우지 않는다")
    parser.add_argument("--max-bytes", type=int, default=MAX_BYTES, help="작품 JSON 파일 최대 크기 (기본 4 MB)")
    parser.add_argument("--check", nargs="?", const=".", metavar="DIR", help="분할 결과를 검증만 한다")
    args = parser.parse_args()

    if args.check:
        problems = check(Path(args.check), args.max_bytes)
        if problems:
            print("검증 실패:")
            for problem in problems[:40]:
                print(" -", problem)
            return 1
        print("검증 통과: JSON 구조·파일 크기·순번·로컬 흔적 이상 없음")
        return 0

    if not args.source:
        parser.error("원본 HTML 경로가 필요하다")
    result = build_site(Path(args.source), Path(args.out), strip=not args.keep_local, max_bytes=args.max_bytes)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    problems = check(Path(args.out), args.max_bytes)
    if problems:
        print("검증 실패:", *problems[:20], sep="\n - ")
        return 1
    print("검증 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
