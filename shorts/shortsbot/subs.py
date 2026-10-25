"""ASS 자막: 상단 배너 문구, 나레이션 자막, 속마음 자막, 출처."""

ASIDE_COLORS = {"yellow": "FFE14D", "green": "4CFF7A", "pink": "FF6FB5", "red": "FF4D4D", "cyan": "4DE1FF"}


def ass_color(hex_rgb):
    h = hex_rgb.lstrip("#")
    return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def esc(text):
    return text.replace("\\", "＼").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def ts(sec):
    sec = max(0.0, sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def circle(r):
    k = round(r * 0.552)
    return (f"m 0 {-r} b {k} {-r} {r} {-k} {r} 0 b {r} {k} {k} {r} 0 {r} "
            f"b {-k} {r} {-r} {k} {-r} 0 b {-r} {-k} {-k} {-r} 0 {-r}")


ARROW = "m -16 -150 l 16 -150 l 16 -70 l 44 -70 l 0 -10 l -44 -70 l -16 -70"


def build(script, timeline, end, style, credit="", colors=None, marks=()):
    """timeline: [(시작, 끝, 문장)] — 실제 음성 위치에 맞춘 나레이션.
    colors: 틀별 배너 색 {line1_color, line2_color}. marks: [(시작, 끝, x픽셀, y픽셀, 종류)]"""
    st = {**style, **(colors or {})}
    white, black = ass_color("FFFFFF"), ass_color("000000")
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Banner,{st['font']},{st['banner_size']},{ass_color(st['line1_color'])},{white},{black},{black},0,0,0,0,100,100,0,0,1,0,0,8,40,40,{max(20, (st['banner_height'] - st['banner_size'] * 2 - 20) // 2)},1
Style: Narr,{st['sub_font']},{st['narr_size']},{white},{white},{black},&H64000000,-1,0,0,0,100,100,0,0,1,7,3,2,60,60,430,1
Style: Aside,{st['sub_font']},{st['aside_size']},{white},{white},{black},{black},-1,0,0,0,100,100,0,0,1,6,0,5,80,80,0,1
Style: Dlg,{st['sub_font']},{st['aside_size']},{white},{white},{black},{black},-1,0,0,0,100,100,0,0,1,6,0,5,70,70,0,1
Style: Mark,Arial,20,{ass_color("FF2D2D")},{white},{ass_color("FF2D2D")},{black},0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1
Style: Credit,{st['sub_font']},34,{white},{white},{black},{black},0,0,0,0,100,100,0,0,1,2,0,3,40,40,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    l2 = ass_color(st["line2_color"])
    ev.append(f"Dialogue: 5,{ts(0)},{ts(end)},Banner,,0,0,0,,{esc(script.banner_line1)}\\N{{\\c{l2}}}{esc(script.banner_line2)}")
    pop = "{\\fscx86\\fscy86\\t(0,90,\\fscx100\\fscy100)}"
    for s, e, text in timeline:
        ev.append(f"Dialogue: 3,{ts(s)},{ts(e)},Narr,,0,0,0,,{pop}{esc(text)}")
    for a in script.asides:
        c = ass_color(ASIDE_COLORS.get(a.color, "FFE14D"))
        jump = "{\\fscx70\\fscy70\\t(0,120,\\fscx108\\fscy108)\\t(120,200,\\fscx100\\fscy100)}"
        ev.append(f"Dialogue: 4,{ts(a.start)},{ts(a.end)},Aside,,0,0,0,,{jump}{{\\c{c}\\pos(540,880)}}{esc(a.text)}")
    for d in getattr(script, "dialogue", []):
        c = ass_color(ASIDE_COLORS.get(d.color, "4CFF7A"))
        ev.append(f"Dialogue: 4,{ts(d.start)},{ts(d.end)},Dlg,,0,0,0,,{{\\c{c}\\pos(540,1230)}}\"{esc(d.text)}\"")
    for a, b, x, y, kind in marks:
        if kind == "circle":
            ev.append(f"Dialogue: 6,{ts(a)},{ts(b)},Mark,,0,0,0,,{{\\pos({x},{y})\\1a&HFF&\\bord9\\fscx60\\fscy60"
                      f"\\t(0,140,\\fscx105\\fscy105)\\t(140,220,\\fscx100\\fscy100)\\p1}}{circle(120)}{{\\p0}}")
        else:
            ev.append(f"Dialogue: 6,{ts(a)},{ts(b)},Mark,,0,0,0,,{{\\bord3\\3c&H000000&"
                      f"\\move({x},{y - 40},{x},{y},0,180)\\p1}}{ARROW}{{\\p0}}")
    ending = getattr(script, "ending_caption", "")
    if ending:
        y = ass_color("FFE14D")
        ev.append(f"Dialogue: 5,{ts(max(0, end - 1.6))},{ts(end)},Aside,,0,0,0,,{{\\c{y}\\pos(540,960)\\fad(120,0)}}{esc(ending)}")
    if credit:
        ev.append(f"Dialogue: 2,{ts(0)},{ts(end)},Credit,,0,0,0,,출처 {esc(credit)}")
    return head + "\n".join(ev) + "\n"
