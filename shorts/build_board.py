"""쇼츠 대기판(아티팩트) HTML 생성.

  python shorts/build_board.py [--out 경로]

state/candidates.json(허가 대기), state/history.json(완성본) 을 읽어 한 장짜리 페이지로 만든다.
썸네일·포스터는 data URI 로 박아 넣는다(아티팩트는 외부 이미지를 막는다).
페이지의 버튼은 아티팩트 db 의 approve / reject / uploaded 컬렉션에 기록하고,
세션이 그것을 내려 받아 `run.py sync` 로 반영한다.
"""
import argparse
import base64
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shortsbot.common import STATE, load_config, load_history  # noqa: E402
from shortsbot.upload import KST  # noqa: E402


def data_uri(p):
    return "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode() if p.exists() else ""


def slots_for(n, cfg):
    now = dt.datetime.now(KST)
    out, day = [], now.date()
    while len(out) < n:
        for hm in cfg["channel"]["slots_kst"]:
            h, m = map(int, hm.split(":"))
            t = dt.datetime(day.year, day.month, day.day, h, m, tzinfo=KST)
            if t > now:
                out.append(t.strftime("%-m/%-d %H:%M"))
                if len(out) == n:
                    break
        day += dt.timedelta(days=1)
    return out


def collect():
    cfg = load_config()
    cpath = STATE / "candidates.json"
    cands = json.loads(cpath.read_text(encoding="utf-8")) if cpath.exists() else []
    cands.sort(key=lambda c: (-(c.get("score") or 0), -c["views"]))
    for c in cands:
        c["thumb"] = data_uri(STATE / "thumbs" / c["thumb"]) if c.get("thumb") else ""
        c.pop("desc", None)
    vids = [v for v in load_history()["videos"] if not v.get("video_id")]
    waiting = [v for v in vids if not v.get("uploaded_manual")]
    slots = slots_for(len(waiting), cfg)
    items = []
    for v in reversed(vids[-60:]):
        items.append({
            "id": v["id"], "title": v["title"], "description": v["description"],
            "tags": ", ".join(v.get("tags") or [h.lstrip("#") for h in v.get("hashtags", [])]),
            "comment": v.get("pinned_comment", ""), "length": v.get("length"),
            "url": v.get("download_url", ""), "src": v.get("url", ""),
            "poster": data_uri(STATE / "posters" / f"{v['id']}.jpg"),
            "done": bool(v.get("uploaded_manual")), "hook": v.get("hook_type", ""),
        })
    for it, s in zip([i for i in reversed(items) if not i["done"]], slots):
        it["slot"] = s
    return {"built": dt.datetime.now(KST).strftime("%-m/%-d %H:%M"), "daily": cfg["channel"]["daily_count"],
            "cands": cands, "items": items}


PAGE = r"""<title>쇼츠 대기판</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Black+Han+Sans&family=IBM+Plex+Sans+KR:wght@400;600&family=IBM+Plex+Mono:wght@500&display=swap">
<style>
/* 편집실 큐시트: 검정 잉크·흰 종이·하늘색 한 가지로 '할 일'만 표시. 슬레이트 머리띠, 타임코드는 고정폭. */
:root{
  --paper:#FAFBFC; --ink:#0B0D10; --sub:#5A6470; --line:#DDE3EA; --well:#EEF2F6;
  --sky:#2E9BEA; --sky-ink:#FFFFFF; --sky-soft:#E3F2FD; --ok:#1F8A4C; --no:#B3261E;
  --display:"Black Han Sans","Apple SD Gothic Neo","Malgun Gothic",sans-serif;
  --body:"IBM Plex Sans KR","Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,Menlo,monospace;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --paper:#0C0E11; --ink:#F2F4F7; --sub:#98A3AF; --line:#262B32; --well:#161A1F;
  --sky:#5BB8F5; --sky-ink:#06121C; --sky-soft:#10283A; --ok:#5FD08F; --no:#F2867E; color-scheme:dark}}
:root[data-theme="dark"]{
  --paper:#0C0E11; --ink:#F2F4F7; --sub:#98A3AF; --line:#262B32; --well:#161A1F;
  --sky:#5BB8F5; --sky-ink:#06121C; --sky-soft:#10283A; --ok:#5FD08F; --no:#F2867E; color-scheme:dark}
body{background:var(--paper);color:var(--ink);font:15px/1.55 var(--body)}
.wrap{max-width:820px;margin:0 auto;padding-block:20px 64px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
.slate{display:grid;grid-template-columns:1fr auto;gap:4px 16px;align-items:end;border-bottom:3px solid var(--ink);padding-bottom:12px}
.slate h1{font:400 34px/1 var(--display);margin:0;letter-spacing:-.01em}
.slate .meta{font:500 12px/1.4 var(--mono);color:var(--sub);text-align:right}
.stripes{height:10px;margin-top:6px;background:repeating-linear-gradient(-45deg,var(--ink) 0 12px,transparent 12px 24px);opacity:.9}
nav{display:flex;gap:0;margin:18px 0 6px;border:1px solid var(--ink)}
nav button{flex:1;min-width:0;padding:10px 6px;border:0;background:transparent;color:var(--ink);font:600 14px var(--body);cursor:pointer}
nav button+button{border-left:1px solid var(--ink)}
nav button[aria-selected="true"]{background:var(--ink);color:var(--paper)}
nav b{font:500 12px var(--mono);margin-left:4px}
.hint{color:var(--sub);font-size:13px;margin:10px 0 14px}
.row{display:grid;grid-template-columns:var(--thumbw) 1fr;gap:14px;padding:16px 0;border-bottom:1px solid var(--line)}
.row>div{min-width:0}
.poster{width:108px;aspect-ratio:9/16;max-width:100%;background:var(--well);object-fit:cover;display:block}
.thumb{width:150px;aspect-ratio:16/9;max-width:100%;background:var(--well);object-fit:cover;display:block}
h2{font:600 16px/1.35 var(--body);margin:0 0 4px;text-wrap:balance}
.tc{font:500 12px var(--mono);color:var(--sub);display:flex;flex-wrap:wrap;gap:4px 12px;margin-bottom:8px}
.tc .slot{color:var(--sky)}
.copy{display:grid;grid-template-columns:64px 1fr auto;gap:8px;align-items:center;padding:6px 0;border-top:1px dashed var(--line)}
.copy .k{font:500 11px var(--mono);letter-spacing:.06em;color:var(--sub);text-transform:uppercase}
.copy .v{min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:13px}
.btn{border:1px solid var(--ink);background:transparent;color:var(--ink);font:600 13px var(--body);padding:6px 12px;cursor:pointer;white-space:nowrap}
.btn:focus-visible,nav button:focus-visible,input:focus-visible{outline:2px solid var(--sky);outline-offset:2px}
.btn.go{background:var(--sky);border-color:var(--sky);color:var(--sky-ink)}
.btn.done{border-color:var(--ok);color:var(--ok)}
.btn.no{border-color:var(--line);color:var(--sub)}
.actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;align-items:center}
a.dl{font:600 13px var(--body);color:var(--sky)}
.score{font:500 12px var(--mono);color:var(--ink)}
.plat{font:600 11px var(--body);padding:1px 6px;border:1px solid var(--sky);color:var(--sky)}
.score i{font-style:normal;color:var(--line)}
.why{color:var(--sub);font-size:13px}
input[type=text]{flex:1 1 200px;min-width:0;border:1px solid var(--line);background:var(--paper);color:var(--ink);padding:7px 9px;font:14px var(--body)}
.chip{font:600 12px var(--body);padding:3px 8px;border:1px solid currentColor}
.chip.ok{color:var(--ok)}.chip.no{color:var(--no)}
.empty{padding:32px 0;color:var(--sub)}
.toast{position:fixed;left:50%;bottom:calc(20px + env(safe-area-inset-bottom,0px));transform:translateX(-50%);background:var(--ink);color:var(--paper);padding:8px 14px;font:600 13px var(--body);opacity:0;transition:opacity .2s;pointer-events:none}
.toast.on{opacity:1}
@media (max-width:520px){.row{--thumbw:96px!important}.poster{width:96px}.thumb{width:96px;aspect-ratio:1}.copy{grid-template-columns:52px 1fr auto}.slate h1{font-size:28px}}
@media (prefers-reduced-motion:reduce){.toast{transition:none}}
</style>
<div class="wrap">
  <header>
    <div class="slate"><h1>쇼츠 대기판</h1><div class="meta" id="meta"></div></div>
    <div class="stripes" aria-hidden="true"></div>
  </header>
  <nav role="tablist" id="tabs">
    <button role="tab" data-t="up" aria-selected="true">업로드 대기<b id="n-up"></b></button>
    <button role="tab" data-t="ok" aria-selected="false">허가 대기<b id="n-ok"></b></button>
    <button role="tab" data-t="done" aria-selected="false">올린 영상<b id="n-done"></b></button>
  </nav>
  <p class="hint" id="hint"></p>
  <section id="list"></section>
</div>
<div class="toast" id="toast" role="status"></div>
<script>
var D=__DATA__;
var tab='up',DB=null,ST={approve:{},reject:{},uploaded:{}};
try{tab=localStorage.getItem('tab')||'up'}catch(e){}
function $(s){return document.querySelector(s)}
function h(t,a,c){var e=document.createElement(t);for(var k in(a||{}))e.setAttribute(k,a[k]);if(c!=null)e.textContent=c;return e}
function toast(m){var t=$('#toast');t.textContent=m;t.classList.add('on');clearTimeout(toast.t);toast.t=setTimeout(function(){t.classList.remove('on')},1600)}
function copy(txt,label,el){var done=function(){toast(label+' 복사됨')};
  if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(txt).then(done,function(){sel(el)})}else sel(el)}
function sel(el){el.hidden=false;var r=document.createRange();el.style.whiteSpace='normal';r.selectNodeContents(el);var s=getSelection();s.removeAllRanges();s.addRange(r);toast('선택됨 — 길게 눌러 복사')}
function uploaded(i){return i.done||!!ST.uploaded[i.id]}
function save(col,id,val){
  if(!DB){toast('저장 안 됨 — 로그인한 화면에서 눌러 주세요');return Promise.reject()}
  var ref=DB.collection(col).doc(id);
  return (val?ref.set(val):ref.delete()).then(function(){},function(){toast('저장 실패 — 다시 눌러 주세요')})}
function now(){var d=new Date();return d.getFullYear()+'-'+(d.getMonth()+1)+'-'+d.getDate()+' '+d.getHours()+':'+String(d.getMinutes()).padStart(2,'0')}

function upRow(i){
  var r=h('div',{class:'row',style:'--thumbw:108px'});
  var p=i.poster?h('img',{class:'poster',src:i.poster,alt:''}):h('div',{class:'poster'});
  r.appendChild(p);var b=h('div');
  b.appendChild(h('h2',null,i.title));
  var tc=h('div',{class:'tc'});
  if(i.slot&&!uploaded(i))tc.appendChild(h('span',{class:'slot'},'추천 '+i.slot));
  if(i.length)tc.appendChild(h('span',null,i.length+'초'));
  if(i.hook)tc.appendChild(h('span',null,i.hook));
  b.appendChild(tc);
  [['제목',i.title],['설명',i.description],['태그',i.tags],['고정댓글',i.comment]].forEach(function(f){
    if(!f[1])return;var c=h('div',{class:'copy'});c.appendChild(h('span',{class:'k'},f[0]));
    var v=h('span',{class:'v'},f[1]);c.appendChild(v);
    var bt=h('button',{class:'btn',type:'button'},'복사');bt.onclick=function(){copy(f[1],f[0],v)};c.appendChild(bt);b.appendChild(c)});
  var a=h('div',{class:'actions'});
  if(i.url){var l=h('a',{class:'dl',href:i.url,target:'_blank',rel:'noopener'},'영상 받기 ↓');a.appendChild(l)}
  else a.appendChild(h('span',{class:'why'},'영상 파일은 다음 제작 실행 뒤 받기 링크가 생겨요'));
  var u=h('button',{class:'btn '+(uploaded(i)?'done':'go'),type:'button'},uploaded(i)?'업로드함 ✓':'업로드함으로 표시');
  u.onclick=function(){var on=!uploaded(i);if(!on&&i.done){toast('이미 기록된 업로드예요');return}
    ST.uploaded[i.id]=on?{at:now()}:undefined;if(!on)delete ST.uploaded[i.id];render();
    save('uploaded',i.id,on?{at:now()}:null)};
  a.appendChild(u);b.appendChild(a);r.appendChild(b);return r}

function okRow(c){
  var r=h('div',{class:'row',style:c.thumb?'--thumbw:150px':'grid-template-columns:1fr'});
  if(c.thumb)r.appendChild(h('img',{class:'thumb',src:c.thumb,alt:''}));
  var b=h('div');b.appendChild(h('h2',null,c.title));
  var tc=h('div',{class:'tc'});
  var pl={instagram:'인스타',tiktok:'틱톡'}[c.platform]||'유튜브';
  tc.appendChild(h('span',{class:'plat'},pl));
  tc.appendChild(h('span',null,c.channel));tc.appendChild(h('span',null,'조회 '+Number(c.views).toLocaleString('ko-KR')));
  if(c.multiple)tc.appendChild(h('span',null,'평소의 '+c.multiple+'배'));
  if(c.seconds)tc.appendChild(h('span',null,c.seconds+'초'));
  if(c.score){var s=h('span',{class:'score',title:'소재 점수 '+c.score+'/5'});s.textContent='●'.repeat(c.score);var o=h('i',null,'●'.repeat(5-c.score));s.appendChild(o);tc.appendChild(s)}
  b.appendChild(tc);if(c.reason)b.appendChild(h('div',{class:'why'},c.reason));
  var a=h('div',{class:'actions'});
  a.appendChild(h('a',{class:'dl',href:c.url,target:'_blank',rel:'noopener'},'원본 보기 ↗'));
  if(c.channel_url)a.appendChild(h('a',{class:'dl',href:c.channel_url,target:'_blank',rel:'noopener'},'계정 열기 ↗'));
  if(c.dm){var dmv=h('span',{class:'v',hidden:''},c.dm);var dmb=h('button',{class:'btn',type:'button'},'요청 문구 복사');
    dmb.onclick=function(){copy(c.dm,'요청 문구',dmv)};a.appendChild(dmb);a.appendChild(dmv)}
  var ap=ST.approve[c.video_id],rj=ST.reject[c.video_id];
  if(ap){a.appendChild(h('span',{class:'chip ok'},'허가됨 · 다음 제작 때 영상으로'));var un=h('button',{class:'btn no',type:'button'},'취소');
    un.onclick=function(){delete ST.approve[c.video_id];render();save('approve',c.video_id,null)};a.appendChild(un)}
  else if(rj){a.appendChild(h('span',{class:'chip no'},'거절함'));var un2=h('button',{class:'btn no',type:'button'},'되돌리기');
    un2.onclick=function(){delete ST.reject[c.video_id];render();save('reject',c.video_id,null)};a.appendChild(un2)}
  else{var inp=h('input',{type:'text',id:'note-'+c.video_id,placeholder:'허락 받은 곳·날짜 (예: 인스타 DM 10/26)','aria-label':'허락 기록'});
    var go=h('button',{class:'btn go',type:'button'},'허가');
    go.onclick=function(){var n=inp.value.trim();if(!n){inp.focus();toast('허락 받은 곳을 적어 주세요');return}
      ST.approve[c.video_id]={at:now(),note:n};render();save('approve',c.video_id,ST.approve[c.video_id])};
    var no=h('button',{class:'btn no',type:'button'},'거절');
    no.onclick=function(){ST.reject[c.video_id]={at:now()};render();save('reject',c.video_id,ST.reject[c.video_id])};
    a.appendChild(inp);a.appendChild(go);a.appendChild(no)}
  b.appendChild(a);r.appendChild(b);return r}

function render(){
  var up=D.items.filter(function(i){return !uploaded(i)}),done=D.items.filter(uploaded);
  var ok=D.cands.filter(function(c){return !ST.reject[c.video_id]||tab==='ok'});
  $('#n-up').textContent=up.length;$('#n-ok').textContent=D.cands.filter(function(c){return !ST.approve[c.video_id]&&!ST.reject[c.video_id]}).length;$('#n-done').textContent=done.length;
  $('#meta').textContent='갱신 '+D.built+' · 하루 '+D.daily+'편';
  document.querySelectorAll('#tabs button').forEach(function(b){b.setAttribute('aria-selected',b.dataset.t===tab)});
  var L=$('#list');L.textContent='';
  var hint={up:'복사 버튼으로 YouTube Studio에 붙여 넣고, 올렸으면 업로드함으로 표시하세요. 추천 시각은 경쟁 채널 업로드 시간대 기준이에요.',
    ok:'계정 열기 → 요청 문구 복사 → DM 보내기. 허락 답장을 받은 영상만 허락 받은 곳·날짜를 적고 허가하세요. 적은 내용은 권리 장부(sources.yml)에 남고, 허가한 영상은 다음 제작 때 만들어져요. 점수는 인기작 50편 분석 기준이에요.',
    done:'업로드함으로 표시한 영상이에요.'}[tab];
  $('#hint').textContent=hint;
  var rows=tab==='up'?up.map(upRow):tab==='ok'?ok.map(okRow):done.map(upRow);
  if(!rows.length)L.appendChild(h('p',{class:'empty'},{up:'올릴 영상이 아직 없어요. 매일 05시 제작이 끝나면 여기에 쌓여요.',ok:'허가 대기 후보가 없어요. 매일 05시 탐색 때 새 후보가 들어와요.',done:'아직 표시한 영상이 없어요.'}[tab]));
  rows.forEach(function(r){L.appendChild(r)})}

document.querySelectorAll('#tabs button').forEach(function(b){b.onclick=function(){tab=b.dataset.t;try{localStorage.setItem('tab',tab)}catch(e){}render()}});
render();
if(window.claude&&window.claude.use){window.claude.use('db').then(function(db){if(!db)return;DB=db;
  ['approve','reject','uploaded'].forEach(function(col){db.collection(col).onSnapshot(function(qs){ST[col]={};qs.docs.forEach(function(d){if(d.exists)ST[col][d.id]=d.data()||{}});render()},function(){})})},function(){})}
</script>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(STATE / "board.html"))
    a = ap.parse_args()
    data = json.dumps(collect(), ensure_ascii=False).replace("</", "<\\/")
    Path(a.out).write_text(PAGE.replace("__DATA__", data), encoding="utf-8")
    print(a.out)


if __name__ == "__main__":
    main()
