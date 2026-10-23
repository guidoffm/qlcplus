"""Erzeugt full-stage-movingheads.qxw aus full-stage.qxw: die 32 Pars werden durch
beamZ MHL-74 Wash (12 Kanäle, RGBW) ersetzt; dazu Grundpositionen, Bewegungen (EFX)
und Auto-Programme, die Farbeffekt, Bewegung und Position kombinieren."""
import math, re, sys

src, dst = sys.argv[1], sys.argv[2]
s = open(src, encoding="utf-8").read()

ids = [0, 1, 4, 5] + list(range(6, 34))          # Ring-Index -> Fixture-ID (wie full-stage)
CH = 12
# Shehds-Kanal -> MHL-74-Kanal (Dimmer, R, G, B, W, Strobe)
REMAP = {0: 4, 1: 5, 2: 6, 3: 7, 4: 8, 5: 10}
PAN, TILT = 0, 2

# --- Geräte
for r, fid in enumerate(ids):
    s = re.sub(rf"<Manufacturer>Shehds</Manufacturer>\s*<Model>[^<]*</Model>\s*<Mode>8ch</Mode>\s*<ID>{fid}</ID>"
               rf"(\s*<Name>[^<]*</Name>\s*<Universe>0</Universe>\s*)<Address>\d+</Address>\s*<Channels>8</Channels>\s*<ForcedHTP>5</ForcedHTP>",
               lambda m: ("<Manufacturer>beamZ</Manufacturer>\n   <Model>MHL-74 Wash 7x10W 4in1 RGBW</Model>\n"
                          f"   <Mode>12 Channel</Mode>\n   <ID>{fid}</ID>{m.group(1)}<Address>{r * CH}</Address>\n"
                          f"   <Channels>{CH}</Channels>\n   <ForcedHTP>10</ForcedHTP>"), s, count=1)
assert s.count("<Manufacturer>beamZ</Manufacturer>") == 32
s = s.replace('<PluginParameters UniverseChannels="256"/>', '<PluginParameters UniverseChannels="384"/>', 1)

# --- Kanalnummern in Szenen und Fadern umrechnen
def remap_pairs(m):
    nums = m.group(2).split(",")
    pairs = [f"{REMAP[int(c)]},{v}" for c, v in zip(nums[::2], nums[1::2])]
    return f'{m.group(1)}{",".join(pairs)}</FixtureVal>'
idset = "|".join(map(str, ids))
s = re.sub(rf'(<FixtureVal ID="(?:{idset})">)([^<]*)</FixtureVal>', remap_pairs, s)
s = re.sub(rf'(<Channel Fixture="(?:{idset})">)(\d)(</Channel>)',
           lambda m: f"{m.group(1)}{REMAP[int(m.group(2))]}{m.group(3)}", s)

# --- 3D: QLC+ zeigt Moving Heads ohne Drehung bereits hängend. Das Modell wird auf die
# Gerätemaße skaliert (Faktor 0,162): 130 x 175 x 97 mm, Mitte 8 mm unter dem Ursprung.
# Oberkante = YPos + 167 mm soll an der Traversenunterkante (3,0 m) liegen.
HANG_Y = 3000 - 167
EDGE = 2650             # unter der Traversenmitte

def head_xz(r):
    """Mitte des Kopfes in Metern (x nach rechts, z nach vorne)."""
    side, i = divmod(r, 8)
    a = -2.1875 + 0.625 * i
    e = EDGE / 1000
    return {0: (a, e), 1: (e, -a), 2: (-a, -e), 3: (-e, a)}[side]

def fx_item(r, fid):
    x, z = head_xz(r)
    return (f'   <FxItem ID="{fid}" XPos="{round(x * 1000 + 2500 - 65)}" YPos="{HANG_Y}" '
            f'ZPos="{round(z * 1000 + 2500 - 49)}"/>\n')
s = re.sub(r'(   <FxItem ID="(\d+)" XPos="-?\d+" YPos="\d+" ZPos="-?\d+" [XZ]Rot="-?\d+"/>\n)',
           lambda m: fx_item(ids.index(int(m.group(2))), int(m.group(2))), s)

# --- Ausrichtung: Pan 540°, Tilt 180°, Tilt 128 = senkrecht nach unten (hängend).
# In der 3D-Ansicht eingemessen: Pan 270° neigt nach links (-x), Pan 360° nach vorne (+z);
# Tilt > 128 neigt in Pan-Richtung.
PAN_ZERO_DEG = 360      # Pan-Wert (Grad), bei dem der Kopf nach vorne (+z) neigt
PAN_SIGN = 1            # +1: Pan dreht von vorne nach rechts
TILT_SIGN = 1           # +1: Tilt > 128 neigt in Blickrichtung
HEIGHT = 2.9

def aim(r, tx, tz, ty):
    """Pan/Tilt-DMX (16 Bit) für Kopf r auf Zielpunkt (tx, ty, tz)."""
    x, z = head_xz(r)
    dx, dz = tx - x, tz - z
    horiz = math.hypot(dx, dz)
    heading = math.degrees(math.atan2(dx, dz))          # 0 = vorne, 90 = rechts
    pan_deg = PAN_ZERO_DEG + PAN_SIGN * heading         # heading -180..180 -> 180..540°
    if pan_deg > 450:                                   # Arbeitsbereich 90..450°: Platz für Bewegungen
        pan_deg -= 360
    off = math.degrees(math.atan2(horiz, HEIGHT - ty))
    pan = round(pan_deg / 540 * 65535)
    tilt = round(32768 + TILT_SIGN * off / 180 * 65535)
    return max(0, min(65535, pan)), max(0, min(65535, tilt))

# Zielpunkte (x, z, Höhe) je Kopf
POSITIONS = [
    ("Mitte", lambda r: (0.0, 0.0, 0.0)),
    ("Senkrecht", lambda r: (*head_xz(r), 0.0)),
    ("Kreuz", lambda r: (head_xz(r)[0], 0.0, 0.0) if r // 8 in (0, 2) else (0.0, head_xz(r)[1], 0.0)),
    ("Publikum", lambda r: (head_xz(r)[0] * 1.6, 6.0, 1.5)),
]

FIRST_FN = 89
funcs = ""
pos_ids = []
for k, (name, target) in enumerate(POSITIONS):
    fid = FIRST_FN + k
    pos_ids.append(fid)
    vals = ""
    for r, fxid in enumerate(ids):
        pan, tilt = aim(r, *target(r))
        vals += f'   <FixtureVal ID="{fxid}">0,{pan >> 8},1,{pan & 255},2,{tilt >> 8},3,{tilt & 255}</FixtureVal>\n'
    funcs += (f'  <Function ID="{fid}" Type="Scene" Name="Position – {name}" Path="Moving Heads/Position">\n'
              f'   <Speed FadeIn="1000" FadeOut="0" Duration="0"/>\n{vals}  </Function>\n')

# --- Bewegungen (EFX, relativ zur aktiven Position)
MOVES = [
    ("Kreis", "Circle", "Parallel", 12, 14, 1, 1, 4000),
    ("Kreiswelle", "Circle", "Asymmetric", 12, 14, 1, 1, 4000),
    ("Acht", "Eight", "Asymmetric", 14, 12, 1, 1, 6000),
    ("Schwenk", "Line", "Parallel", 20, 0, 1, 1, 4000),
    ("Welle", "Line", "Asymmetric", 0, 18, 1, 1, 3000),
    ("Lissajous", "Lissajous", "Asymmetric", 12, 14, 2, 3, 8000),
    ("Raute", "Diamond", "Parallel", 12, 14, 1, 1, 4000),
    ("Blatt", "Leaf", "Asymmetric", 12, 14, 1, 1, 6000),
]
move_ids = []
for k, (name, algo, prop, w, h, fx, fy, dur) in enumerate(MOVES):
    fid = FIRST_FN + len(POSITIONS) + k
    move_ids.append(fid)
    fixtures = "".join(f"   <Fixture>\n    <ID>{fxid}</ID>\n    <Head>0</Head>\n    <Mode>0</Mode>\n"
                       f"    <Direction>Forward</Direction>\n    <StartOffset>0</StartOffset>\n   </Fixture>\n"
                       for fxid in ids)
    rot = 90 if name == "Welle" else 0
    funcs += (f'  <Function ID="{fid}" Type="EFX" Name="Bewegung – {name}" Path="Moving Heads/Bewegung">\n'
              f'{fixtures}   <PropagationMode>{prop}</PropagationMode>\n'
              f'   <Speed FadeIn="0" FadeOut="0" Duration="{dur}"/>\n   <Direction>Forward</Direction>\n'
              f'   <RunOrder>Loop</RunOrder>\n   <Algorithm>{algo}</Algorithm>\n   <Width>{w}</Width>\n'
              f'   <Height>{h}</Height>\n   <Rotation>{rot}</Rotation>\n   <StartOffset>0</StartOffset>\n'
              f'   <IsRelative>1</IsRelative>\n   <DimmerControl>0</DimmerControl>\n'
              f'   <Axis Name="X">\n    <Offset>127</Offset>\n    <Frequency>{fx}</Frequency>\n    <Phase>90</Phase>\n   </Axis>\n'
              f'   <Axis Name="Y">\n    <Offset>127</Offset>\n    <Frequency>{fy}</Frequency>\n    <Phase>0</Phase>\n   </Axis>\n'
              f'  </Function>\n')

# --- Auto-Programme: Collections aus Farbeffekt + Bewegung + Position
effects = list(range(59, 67)) + list(range(73, 89))
coll_ids = []
for k, eff in enumerate(effects):
    fid = FIRST_FN + len(POSITIONS) + len(MOVES) + k
    coll_ids.append(fid)
    steps = [eff, move_ids[k % len(MOVES)], pos_ids[(k // 2) % len(POSITIONS)]]
    funcs += (f'  <Function ID="{fid}" Type="Collection" Name="Auto-Show {k + 1}" Path="Moving Heads/Auto">\n'
              + "".join(f'   <Step Number="{n}">{f}</Step>\n' for n, f in enumerate(steps)) + "  </Function>\n")
s = s.replace("  <Monitor ", funcs + "  <Monitor ", 1)

def auto_steps(m):
    head = re.sub(r'   <Step Number=.*?</Step>\n', "", m.group(0))
    steps = "".join(f'   <Step Number="{n}" FadeIn="0" Hold="0" FadeOut="0">{f}</Step>\n'
                    for n, f in enumerate(coll_ids))
    return head.replace("  </Function>\n", steps + "  </Function>\n")
s = re.sub(r'  <Function ID="(6[7-9]|7[0-2])" Type="Chaser" Name="Auto.*?</Function>\n', auto_steps, s, flags=re.S)

# --- Pult: SoloFrames "Position" (Pads Noten 40-43) und "Bewegung" (Noten 8-15)
FIRST_WIDGET = 75
def button(wid, caption, fid, x, y, argb, channel, fb, upper):
    return f"""    <Button Caption="{caption}" ID="{wid}">
     <WindowState Visible="True" X="{x}" Y="{y}" Width="102" Height="102"/>
     <Appearance>
      <ForegroundColor>4278190080</ForegroundColor>
      <BackgroundColor>{argb}</BackgroundColor>
     </Appearance>
     <Function ID="{fid}"/>
     <Action>Toggle</Action>
     <Input ID="0" Universe="0" Channel="{channel}" LowerValue="{fb}" UpperValue="{fb}" MonitorValue="{fb}" LowerParams="1" UpperParams="{upper}" MonitorParams="{upper}"/>
    </Button>
"""
def frame(wid, caption, x, y, w, h, body):
    return f"""   <SoloFrame Caption="{caption}" ID="{wid}">
    <WindowState Visible="True" X="{x}" Y="{y}" Width="{w}" Height="{h}"/>
    <AllowResize>True</AllowResize>
    <ShowHeader>False</ShowHeader>
    <ShowEnableButton>True</ShowEnableButton>
    <Collapsed>False</Collapsed>
    <Disabled>False</Disabled>
{body}   </SoloFrame>
"""
wid = FIRST_WIDGET
body = ""
for k, (name, _) in enumerate(POSITIONS):
    body += button(wid, name, pos_ids[k], 24 + 126 * (k % 2), 24 + 126 * (k // 2), 4294967295, 128 + 40 + k, 6, 6)
    wid += 1
pos_frame = frame(wid, "Position", 1520, 222, 276, 276, body); wid += 1
body = ""
for k, mv in enumerate(MOVES):
    body += button(wid, mv[0], move_ids[k], 24 + 126 * (k % 2), 24 + 126 * (k // 2), 4278255360, 128 + 8 + k, 42, 9)
    wid += 1
move_frame = frame(wid, "Bewegung", 1520, 522, 276, 528, body)
s = s.replace('   <Frame Caption="Show Wizard" ID="4">', pos_frame + move_frame + '   <Frame Caption="Show Wizard" ID="4">', 1)

# --- Farb-Pads neu ordnen: Reihe 1 (Noten 56-62) und Reihe 2 (48-53), Strobe bleibt auf 63
COLOR_NOTES = {"Red": 56, "Green": 57, "Blue": 58, "Cyan": 59, "Magenta": 60, "Yellow": 61, "Amber": 62,
               "Orange": 48, "Lime": 49, "White": 50, "White LED": 51, "Pink": 52, "Purple": 53}
colors_frame = re.search(r'<SoloFrame Caption="Colors" ID="9">.*?</SoloFrame>', s, re.S).group(0)
new_frame = colors_frame
for cap, note in COLOR_NOTES.items():
    new_frame = re.sub(rf'(<Button Caption="{cap}" ID="\d+">.*?<Input ID="0" Universe="0" Channel=")\d+"',
                       lambda m: f'{m.group(1)}{128 + note}"', new_frame, count=1, flags=re.S)
s = s.replace(colors_frame, new_frame)

# --- Pult-Seite "APC": einzige Pult-Seite, aufgebaut wie der APC mini mk2. Tasten und Fader
# werden mit ihren MIDI-Zuordnungen von Seite 1 übernommen; Seite 1 entfällt danach.
page1_start = s.index('  <Frame Caption="Seite 1" ID="0">')
page1_end = s.index('  <Frame Caption="Seite 2" ID="1">')
page1 = s[page1_start:page1_end]
mapped = {}
for m in re.finditer(r'<Button Caption="([^"]*)" ID="(\d+)">(.*?)</Button>', page1, re.S):
    body = m.group(3)
    ch = re.search(r'<Input ID="0" Universe="0" Channel="(\d+)"[^>]*/>', body)
    if not ch or 'Visible="False"' in body or not 0 <= int(ch.group(1)) - 128 < 128:
        continue
    bg = re.search(r'<BackgroundColor>(\d+)</BackgroundColor>', body)
    mapped[int(ch.group(1)) - 128] = dict(
        caption=m.group(1), id=m.group(2), bg=bg.group(1) if bg else "4282664004",
        rest=re.search(r'(<Function ID="\d+"/>.*)', body, re.S).group(1).strip())
sliders = {}
for m in re.finditer(r'<Slider Caption="([^"]*)" ID="(\d+)"([^>]*)>(.*?)</Slider>', page1, re.S):
    ch = re.search(r'<Input ID="0" Universe="0" Channel="(\d+)"/>', m.group(4))
    if ch and 'Visible="False"' not in m.group(4):
        bg = re.search(r'<BackgroundColor>(\d+)</BackgroundColor>', m.group(4))
        sliders[int(ch.group(1)) - 48] = dict(caption=m.group(1), id=m.group(2), attrs=m.group(3),
                                              bg=bg.group(1) if bg else "4282664004",
                                              rest=m.group(4)[m.group(4).index("<Input"):].rstrip())

FONT = "Roboto Condensed,11,-1,5,600,0,0,0,0,0,0,0,0,0,0,1"
PAD_W, PAD_H, GAP, X0, Y0 = 104, 72, 8, 40, 40
next_id = 200
def new_id():
    global next_id
    next_id += 1
    return next_id

def appearance(fg, bg):
    return (f'<Appearance>\n     <Font>{FONT}</Font>\n     <ForegroundColor>{fg}</ForegroundColor>\n'
            f'     <BackgroundColor>{bg}</BackgroundColor>\n    </Appearance>')

def widget(note, x, y, w, h, empty_caption=""):
    if note in mapped:
        b = mapped[note]
        c = int(b["bg"])                   # helle Schrift auf dunklem Hintergrund
        lum = 0.3 * (c >> 16 & 255) + 0.59 * (c >> 8 & 255) + 0.11 * (c & 255)
        fg = "4278190080" if lum > 90 else "4294967295"
        return (f'   <Button Caption="{b["caption"]}" ID="{b["id"]}">\n'
                f'    <WindowState Visible="True" X="{x}" Y="{y}" Width="{w}" Height="{h}"/>\n'
                f'    {appearance(fg, b["bg"])}\n    {b["rest"]}\n   </Button>\n')
    return (f'   <Label Caption="{empty_caption}" ID="{new_id()}">\n'
            f'    <WindowState Visible="True" X="{x}" Y="{y}" Width="{w}" Height="{h}"/>\n'
            f'    {appearance("4288256409", "4280558628")}\n   </Label>\n')

def cell(row, col):
    return X0 + col * (PAD_W + GAP), Y0 + row * (PAD_H + GAP)

# Gruppen, in denen immer nur eine Taste aktiv ist: (Name, erste Reihe, letzte Reihe, Spalten)
SOLO = [("Farben", 0, 1, 7), ("Positionen", 2, 2, 4), ("Effekte", 3, 5, 8),
        ("Bewegung", 6, 6, 8), ("Auto", 7, 7, 6)]
in_solo = set()
widgets = ""
for name, r0, r1, ncol in SOLO:
    fx, fy = cell(r0, 0)
    inner = ""
    for row in range(r0, r1 + 1):
        for col in range(ncol):
            in_solo.add((row, col))
            x, y = cell(row, col)
            inner += widget((7 - row) * 8 + col, x - fx + 4, y - fy + 4, PAD_W, PAD_H)
    widgets += (f'   <SoloFrame Caption="{name}" ID="{new_id()}">\n'
                f'    <WindowState Visible="True" X="{fx - 4}" Y="{fy - 4}" '
                f'Width="{ncol * (PAD_W + GAP) - GAP + 8}" Height="{(r1 - r0 + 1) * (PAD_H + GAP) - GAP + 8}"/>\n'
                f'    <AllowResize>False</AllowResize>\n    <ShowHeader>False</ShowHeader>\n'
                f'    <ShowEnableButton>False</ShowEnableButton>\n    <Collapsed>False</Collapsed>\n'
                f'    <Disabled>False</Disabled>\n' + inner.replace("\n   <", "\n    <").replace("   <Button", "    <Button", 1)
                + '   </SoloFrame>\n')
for row in range(8):
    for col in range(8):
        if (row, col) not in in_solo:
            widgets += widget((7 - row) * 8 + col, *cell(row, col), PAD_W, PAD_H)
SCENE = ["CLIP STOP", "SOLO", "MUTE", "REC ARM", "SELECT", "DRUM", "NOTE", "STOP ALL"]
xs = X0 + 8 * (PAD_W + GAP) + 16
for i, name in enumerate(SCENE):           # rechte Spalte, Noten 112-119
    widgets += widget(112 + i, xs, Y0 + i * (PAD_H + GAP) + 16, 104, 40, name)
yt = Y0 + 8 * (PAD_H + GAP) + 8
widgets += widget(122, xs, yt, 104, 40, "SHIFT")
TRACK = ["VOLUME", "PAN", "SEND", "DEVICE", "▲", "▼", "◀", "▶"]
for i, name in enumerate(TRACK):           # untere Reihe, Noten 100-107
    widgets += widget(100 + i, X0 + i * (PAD_W + GAP), yt, PAD_W, 40, name)
yf = yt + 56
for i in range(9):                         # Fader 1-8 und Master (CC 48-56)
    x = X0 + i * (PAD_W + GAP) + (16 if i == 8 else 0)
    if i in sliders:
        sl = sliders[i]
        widgets += (f'   <Slider Caption="{sl["caption"]}" ID="{sl["id"]}"{sl["attrs"]}>\n'
                    f'    <WindowState Visible="True" X="{x}" Y="{yf}" Width="{PAD_W}" Height="250"/>\n'
                    f'    {appearance("4294967295", sl["bg"])}\n    {sl["rest"]}\n   </Slider>\n')
    else:
        widgets += (f'   <Label Caption="{"MASTER" if i == 8 else i + 1}" ID="{new_id()}">\n'
                    f'    <WindowState Visible="True" X="{x}" Y="{yf}" Width="{PAD_W}" Height="250"/>\n'
                    f'    {appearance("4288256409", "4280558628")}\n   </Label>\n')

page2_end = s.index("  </Frame>\n", page1_end)
page2 = s[page1_end:page2_end].replace('Caption="Seite 2"', 'Caption="APC"')
s = s[:page1_start] + page2 + widgets + s[page2_end:]
s = re.sub(r'  <Frame Caption="Seite [34]" ID="\d+">.*?\n  </Frame>\n', "", s, flags=re.S)  # leere Seiten
print("APC-Seite:", len(mapped), "Tasten,", len(sliders), "Fader")

open(dst, "w", encoding="utf-8").write(s)
print("ok:", len(POSITIONS), "Positionen,", len(MOVES), "Bewegungen,", len(coll_ids), "Auto-Shows")
