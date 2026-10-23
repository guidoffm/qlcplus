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

# --- Pult-Seite "APC": beschriftetes Abbild der APC-Belegung (ohne eigene MIDI-Eingänge;
# die Tasten auf Seite 1 bekommen die Pads, ihre SoloFrames stoppen auch von hier gestartete Funktionen)
page1 = s[s.index('<Frame Caption="Seite 1" ID="0">'):s.index('<Frame Caption="Seite 2" ID="1">')]
mapped = {}
for m in re.finditer(r'<Button Caption="([^"]*)" ID="\d+">(.*?)</Button>', page1, re.S):
    body = m.group(2)
    ch = re.search(r'<Input ID="0" Universe="0" Channel="(\d+)"', body)
    if not ch or 'Visible="False"' in body:
        continue
    note = int(ch.group(1)) - 128
    bg = re.search(r'<BackgroundColor>(\d+)</BackgroundColor>', body)
    mapped[note] = dict(caption=m.group(1), function=re.search(r'<Function ID="(\d+)"/>', body).group(1),
                        action=re.search(r'(<Action[^>]*>[^<]*</Action>)', body).group(1),
                        bg=bg.group(1) if bg else "4282664004")

FONT = "Roboto Condensed,11,-1,5,600,0,0,0,0,0,0,0,0,0,0,1"
wid = 200
def apc_widget(note, x, y, w, h, empty_caption=""):
    global wid
    wid += 1
    if note in mapped:
        b = mapped[note]
        c = int(b["bg"])                   # helle Schrift auf dunklem Hintergrund
        lum = 0.3 * (c >> 16 & 255) + 0.59 * (c >> 8 & 255) + 0.11 * (c & 255)
        fg = "4278190080" if lum > 90 else "4294967295"
        return (f'   <Button Caption="{b["caption"]}" ID="{wid}">\n'
                f'    <WindowState Visible="True" X="{x}" Y="{y}" Width="{w}" Height="{h}"/>\n'
                f'    <Appearance>\n     <Font>{FONT}</Font>\n     <ForegroundColor>{fg}</ForegroundColor>\n'
                f'     <BackgroundColor>{b["bg"]}</BackgroundColor>\n    </Appearance>\n'
                f'    <Function ID="{b["function"]}"/>\n    {b["action"]}\n   </Button>\n')
    return (f'   <Label Caption="{empty_caption}" ID="{wid}">\n'
            f'    <WindowState Visible="True" X="{x}" Y="{y}" Width="{w}" Height="{h}"/>\n'
            f'    <Appearance>\n     <Font>{FONT}</Font>\n     <ForegroundColor>4288256409</ForegroundColor>\n'
            f'     <BackgroundColor>4280558628</BackgroundColor>\n    </Appearance>\n   </Label>\n')

PAD_W, PAD_H, GAP, X0, Y0 = 104, 72, 8, 40, 40
widgets = ""
for row in range(8):                       # oben = Noten 56-63
    for col in range(8):
        note = (7 - row) * 8 + col
        widgets += apc_widget(note, X0 + col * (PAD_W + GAP), Y0 + row * (PAD_H + GAP), PAD_W, PAD_H)
SCENE = ["CLIP STOP", "SOLO", "MUTE", "REC ARM", "SELECT", "DRUM", "NOTE", "STOP ALL"]
xs = X0 + 8 * (PAD_W + GAP) + 16
for i, name in enumerate(SCENE):           # rechte Spalte, Noten 112-119
    widgets += apc_widget(112 + i, xs, Y0 + i * (PAD_H + GAP) + 16, 104, 40, name)
widgets += apc_widget(122, xs, Y0 + 8 * (PAD_H + GAP) + 8, 104, 40, "SHIFT")
TRACK = ["VOLUME", "PAN", "SEND", "DEVICE", "▲", "▼", "◀", "▶"]
yt = Y0 + 8 * (PAD_H + GAP) + 8
for i, name in enumerate(TRACK):           # untere Reihe, Noten 100-107
    widgets += apc_widget(100 + i, X0 + i * (PAD_W + GAP), yt, PAD_W, 40, name)
FADERS = ["1\nIntensity", "2\nRot", "3\nGrün", "4\nBlau", "5\nWeiß", "6", "7", "8", "MASTER"]
yf = yt + 56
for i, name in enumerate(FADERS):          # Fader-Beschriftung (CC 48-56)
    x = X0 + i * (PAD_W + GAP) + (16 if i == 8 else 0)
    wid += 1
    widgets += (f'   <Label Caption="{name.replace(chr(10), " · ")}" ID="{wid}">\n'
                f'    <WindowState Visible="True" X="{x}" Y="{yf}" Width="{PAD_W}" Height="56"/>\n'
                f'    <Appearance>\n     <Font>{FONT}</Font>\n     <ForegroundColor>4292927712</ForegroundColor>\n'
                f'     <BackgroundColor>4279900698</BackgroundColor>\n    </Appearance>\n   </Label>\n')
page2_start = s.index('<Frame Caption="Seite 2" ID="1">')
page2_end = s.index("  </Frame>\n", page2_start)
s = s[:page2_start] + s[page2_start:page2_end].replace('Caption="Seite 2"', 'Caption="APC"') + widgets + s[page2_end:]
print("APC-Seite:", len(mapped), "belegte Tasten")

open(dst, "w", encoding="utf-8").write(s)
print("ok:", len(POSITIONS), "Positionen,", len(MOVES), "Bewegungen,", len(coll_ids), "Auto-Shows")
