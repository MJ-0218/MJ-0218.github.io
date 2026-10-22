#!/usr/bin/env python3
"""초안(.md) → 네이버 블로그 / 티스토리에 붙여넣기 좋은 HTML.

네이버 스마트에디터와 티스토리 에디터는 브라우저에서 '서식 있는 텍스트'로 복사한 내용을
그대로 받아 준다. 그래서 인라인 스타일만 쓴 HTML 페이지를 만들고, 상단의 [본문 복사] 버튼으로
클립보드에 text/html 로 복사한다. 열어서 버튼 → 에디터에 Ctrl+V.

사용: python3 automation/scripts/export_paste.py _drafts/파일.md [--site https://도메인]
출력: exports/<파일명>.html
필요: pip install markdown
"""
import html
import re
import sys
from pathlib import Path

try:
    import markdown
except ImportError:
    sys.exit("pip install markdown 먼저 실행하세요.")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
from style_check import split_front_matter  # noqa: E402

STYLE = {
    "h2": "font-size:20px;font-weight:700;margin:32px 0 12px;padding-top:12px;border-top:1px solid #222;",
    "h3": "font-size:17px;font-weight:700;margin:24px 0 8px;",
    "p": "font-size:16px;line-height:1.9;margin:0 0 22px;",
    "li": "font-size:16px;line-height:1.8;",
    "table": "border-collapse:collapse;width:100%;margin:16px 0;font-size:15px;",
    "th": "border-bottom:2px solid #222;padding:8px;text-align:left;",
    "td": "border-bottom:1px solid #999;padding:8px;",
    "blockquote": "border-left:4px solid #7cc8ff;margin:16px 0;padding:4px 0 4px 14px;color:#444;",
}


def fm_value(fm, key):
    m = re.search(rf"^{key}:\s*(.+)$", fm, flags=re.M)
    return m.group(1).strip().strip('"\'') if m else ""


def fm_sources(fm):
    out, title, in_src = [], None, False
    for line in fm.splitlines():
        if re.match(r"^\S", line):  # sources: 블록 안만 (image_requests·images 의 url 은 출처가 아님)
            in_src = line.startswith("sources:")
            continue
        if not in_src:
            continue
        t = re.search(r"title:\s*(.+)$", line)
        u = re.search(r"url:\s*(\S+)", line)
        if line.strip().startswith("- title:") and t:
            title = t.group(1).strip().strip('"\'')
        elif u:
            out.append((title or u.group(1), u.group(1).strip('"\'')))
            title = None
    return out


MAP_BUTTON = ("display:inline-block;padding:10px 16px;background:#7cc8ff;color:#0b0b0c;font-weight:700;"
              "text-decoration:none;border-radius:0;")
MAP_HOSTS = r"(?:map\.naver\.com|map\.kakao\.com|www\.google\.com/maps)"


# 문장 끝: 한글 뒤 . ! ? ~ (이모지가 붙을 수 있음), 이모지로 끝남, ㅎㅎ·ㅋㅋ
_EMOJI = "\U0001F300-\U0001FAFF☀-➿️"
_SENT_END = re.compile(rf"(?<=[가-힣\)][.!?~])\s+(?![{_EMOJI}])|(?<=[가-힣\)][.!?~][{_EMOJI}])\s+|(?<=[가-힣][{_EMOJI}])\s+"
                       rf"|(?<=[.!?~][{_EMOJI}][{_EMOJI}])\s+|(?<=[ㅎㅋ]{{2}})\s+(?![{_EMOJI}])")
_NOT_PARA = re.compile(r"^\s*(#|\||[-*+] |\d+\. |>|<|!\[|\[📍|```)")


def readable_paragraphs(body_md, per_para=2):
    """국내 글 가독성: 평문 문단을 문장마다 줄바꿈하고, 2문장씩 문단을 나눈다 (표·목록·제목·이미지·지도 버튼은 그대로)."""
    out = []
    for block in re.split(r"\n\s*\n", body_md.strip()):
        if _NOT_PARA.match(block) or "\n" in block.strip():
            out.append(block)
            continue
        sents = [s for s in _SENT_END.split(block.strip()) if s]
        if len(sents) <= 1:
            out.append(block)
            continue
        groups = [sents[i:i + per_para] for i in range(0, len(sents), per_para)]
        if len(groups) > 1 and len(groups[-1]) == 1 and len(groups[-2]) == per_para and len(sents) == 3:
            groups = [sents]  # 3문장은 한 문단에 줄바꿈만
        out.extend("  \n".join(g) for g in groups)
    return "\n\n".join(out) + "\n"


def inline_styles(body_html):
    for tag, css in STYLE.items():
        body_html = re.sub(rf"<{tag}(\s[^>]*)?>", lambda m: f'<{tag}{m.group(1) or ""} style="{css}">', body_html)
    # 지도 링크는 눌러 보기 쉽게 하늘색 버튼으로 (새 창)
    body_html = re.sub(rf'<a href="(https://{MAP_HOSTS}[^"]*)">',
                       lambda m: f'<a href="{m.group(1)}" target="_blank" rel="noopener" style="{MAP_BUTTON}">', body_html)
    return body_html


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    site = "https://mj-0218.github.io"
    if "--site" in sys.argv:
        site = sys.argv[sys.argv.index("--site") + 1].rstrip("/")
        args = [a for a in args if a != site and a != site + "/"]
    if not args:
        sys.exit(__doc__)
    src = Path(args[0])
    fm, body = split_front_matter(src.read_text(encoding="utf-8"))
    title = fm_value(fm, "title")
    as_of = fm_value(fm, "info_as_of")
    tool = fm_value(fm, "related_tool")

    body = re.sub(r"\{%.*?%\}|\{\{.*?\}\}", "", body, flags=re.S)
    body = re.sub(r'<div class="callout"[^>]*>', '<div style="border:2px solid #222;padding:14px 16px;margin:16px 0;">', body)
    if fm_value(fm, "lang") != "en":
        body = readable_paragraphs(body)
    body_html = markdown.markdown(body, extensions=["tables", "sane_lists", "md_in_html"])
    body_html = inline_styles(body_html)

    extra = ""
    if tool:
        extra += (f'<p style="{STYLE["p"]}"><b>바로 계산해 보기 →</b> '
                  f'<a href="{site}/tools/{tool}/">{site.replace("https://", "")}/tools/{tool}/</a></p>')
    sources = fm_sources(fm)
    if sources:
        items = "".join(f'<li style="{STYLE["li"]}"><a href="{html.escape(u)}">{html.escape(t)}</a></li>' for t, u in sources)
        extra += f'<p style="{STYLE["p"]}margin-top:28px;"><b>출처</b></p><ol>{items}</ol>'
    if as_of:
        extra += f'<p style="{STYLE["p"]}color:#777;font-size:14px;">정보 기준일: {html.escape(as_of)}</p>'

    page = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)} — 붙여넣기용</title>
<style>body{{margin:0;background:#f3eee2;font-family:'Apple SD Gothic Neo','Malgun Gothic',sans-serif;color:#16130f}}
.bar{{position:sticky;top:0;display:flex;gap:10px;align-items:center;padding:12px 16px;background:#16130f;color:#f3eee2;flex-wrap:wrap}}
.bar button{{font:700 15px sans-serif;padding:10px 16px;border:0;background:#cf3a1f;color:#fff;cursor:pointer}}
.bar span{{font-size:13px;opacity:.8}}#post{{max-width:720px;margin:24px auto;padding:24px 16px;background:#fff}}</style></head>
<body><div class="bar"><button id="copy-title">제목 복사</button><button id="copy">본문 복사</button>
<span id="msg">버튼을 누른 뒤 네이버·티스토리 에디터에 Ctrl+V</span></div>
<article id="post"><h1 style="font-size:24px;margin:0 0 20px;">{html.escape(title)}</h1>
<div id="body">{body_html}{extra}</div></article>
<script>
function copyHtml(node,msg){{var h=node.innerHTML,t=node.innerText;
 if(navigator.clipboard&&window.ClipboardItem){{navigator.clipboard.write([new ClipboardItem({{'text/html':new Blob([h],{{type:'text/html'}}),'text/plain':new Blob([t],{{type:'text/plain'}})}})]).then(function(){{document.getElementById('msg').textContent=msg}});}}
 else{{var r=document.createRange();r.selectNodeContents(node);var s=getSelection();s.removeAllRanges();s.addRange(r);document.execCommand('copy');s.removeAllRanges();document.getElementById('msg').textContent=msg}}}}
document.getElementById('copy').onclick=function(){{copyHtml(document.getElementById('body'),'본문 복사됨 — 에디터 본문에 붙여넣기')}};
document.getElementById('copy-title').onclick=function(){{navigator.clipboard.writeText({title!r});document.getElementById('msg').textContent='제목 복사됨'}};
</script></body></html>"""
    out = ROOT / "exports" / (src.stem + ".html")
    out.parent.mkdir(exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(out.relative_to(ROOT))


if __name__ == "__main__":
    main()
