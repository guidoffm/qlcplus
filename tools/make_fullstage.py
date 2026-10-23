"""Erzeugt full-stage.qxw aus externer-trigger.qxw: 4 Traversen x 8 Shehds-Pars."""
import re, sys

src, dst = sys.argv[1], sys.argv[2]
s = open(src, encoding="utf-8").read()

# --- Heads: Ring-Reihenfolge vorne L->R, rechts vorne->hinten, hinten R->L, links hinten->vorne
TRUSSES = [("Vorne", "front"), ("Rechts", "right"), ("Hinten", "rear"), ("Links", "left")]
old_ids = [0, 1, 4, 5]
ids = old_ids + list(range(6, 34))          # Ring-Index -> Fixture-ID
names = [f"{t} {i + 1}" for t, _ in TRUSSES for i in range(8)]

def pos(ring):
    """Mitte jedes Pars unter der Traversenmitte (+-2,65 m); QLC+ speichert die Ecke in mm.
    Par laut Fixture-Definition 118 x 105 x 114 mm, hängt unter der Traverse (Unterkante 3,0 m)."""
    side, i = divmod(ring, 8)
    a = 2500 - 2187 + 625 * i - 59     # links -> rechts bzw. hinten -> vorne
    b = 2500 + 2187 - 625 * i - 59     # umgekehrte Laufrichtung
    near, far = 2500 + 2650 - 57, 2500 - 2650 - 57
    y = 3000 - 105
    return {0: (a, y, near), 1: (near, y, b), 2: (b, y, far), 3: (far, y, a)}[side]

def map_cell(ring):
    """Draufsicht 10x10: vorne unten (y=9), hinten oben (y=0)."""
    side, i = divmod(ring, 8)
    return {0: (1 + i, 9), 1: (9, 8 - i), 2: (8 - i, 0), 3: (0, 1 + i)}[side]

# --- DMX-Ausgabe auf 256 Kanäle
s = s.replace('<PluginParameters UniverseChannels="32"/>', '<PluginParameters UniverseChannels="256"/>', 1)

# --- Fixtures
def fixture_xml(fid, name, addr):
    return f"""  <Fixture>
   <Manufacturer>Shehds</Manufacturer>
   <Model>LED Flat Par 12x3W RGBW Color Lighting</Model>
   <Mode>8ch</Mode>
   <ID>{fid}</ID>
   <Name>{name}</Name>
   <Universe>0</Universe>
   <Address>{addr}</Address>
   <Channels>8</Channels>
   <ForcedHTP>5</ForcedHTP>
  </Fixture>
"""
for ring, fid in enumerate(old_ids):
    s = re.sub(rf"(<ID>{fid}</ID>\s*<Name>)[^<]*(</Name>)", rf"\g<1>{names[ring]}\g<2>", s, 1)
new_fx = "".join(fixture_xml(fid, names[r], r * 8) for r, fid in enumerate(ids) if fid >= 6)
s = s.replace("  <FixtureGroup ID=\"0\">", new_fx + "  <FixtureGroup ID=\"0\">", 1)

# --- Gruppen
def group(gid, name, w, h, cell):
    heads = "".join(f'   <Head X="{cell(r)[0]}" Y="{cell(r)[1]}" Fixture="{fid}">0</Head>\n'
                    for r, fid in enumerate(ids))
    return f'  <FixtureGroup ID="{gid}">\n   <Name>{name}</Name>\n   <Size X="{w}" Y="{h}"/>\n{heads}  </FixtureGroup>\n'
groups = (group(0, "Spots", 10, 10, map_cell)
          + group(1, "All Groups", 10, 10, map_cell)
          + group(2, "Ring", 32, 1, lambda r: (r, 0))
          + group(3, "Traversen", 8, 4, lambda r: (r % 8, r // 8)))
s = re.sub(r"  <FixtureGroup ID=\"0\">.*?</FixtureGroup>\n  <FixtureGroup ID=\"1\">.*?</FixtureGroup>\n",
           lambda m: groups, s, 1, flags=re.S)

# --- Szenen mit FixtureVal: 4 Zeilen -> 32 (A/B-Muster abwechselnd)
def expand_vals(m):
    lines = re.findall(r'   <FixtureVal ID="(\d+)">([^<]*)</FixtureVal>\n', m.group(0))
    vals = dict(lines)
    pattern = [vals["0"], vals["1"]]
    return "".join(f'   <FixtureVal ID="{fid}">{pattern[r % 2]}</FixtureVal>\n' for r, fid in enumerate(ids))
s = re.sub(r'(   <FixtureVal ID="0">[^<]*</FixtureVal>\n)(   <FixtureVal ID="(1|4|5)">[^<]*</FixtureVal>\n){3}',
           expand_vals, s)

# --- Fader-Kanäle: 4 Zeilen -> 32
def expand_channels(m):
    ch = m.group(2)
    return "".join(f'{m.group(1)}<Channel Fixture="{fid}">{ch}</Channel>\n' for fid in ids)
s = re.sub(r'( +)<Channel Fixture="0">(\d+)</Channel>\n(\1<Channel Fixture="(1|4|5)">\2</Channel>\n){3}',
           expand_channels, s)

# --- bestehende Effekte auf passende Gruppen/Tempi
def set_matrix(fid, group=None, duration=None):
    global s
    m = re.search(rf'  <Function ID="{fid}" Type="RGBMatrix".*?</Function>\n', s, re.S)
    block = m.group(0)
    if group is not None:
        block = re.sub(r"<FixtureGroup>\d+</FixtureGroup>", f"<FixtureGroup>{group}</FixtureGroup>", block)
    if duration is not None:
        block = re.sub(r'Duration="\d+"', f'Duration="{duration}"', block)
    s = s.replace(m.group(0), block)
set_matrix(59, 2, 500)   # Lauflicht im Kreis, halber Beat pro Head
set_matrix(60, 2, 500)   # Ping-Pong im Kreis
set_matrix(61, 0)        # Füllen/Leeren quer über die Bühne
set_matrix(62, 2)        # Polizei abwechselnd im Ring
set_matrix(63, 2)        # Regenbogen rund um die Bühne
set_matrix(25, 2); set_matrix(51, 2)

# --- neue Animationen
C = dict(cyan=(4278255615, 74), blue=(4278190335, 90), magenta=(4294902015, 106), white=(4294967295, 6),
         orange=(4294908416, 18), purple=(4286185727, 162), red=(4294901760, 10), pink=(4294910080, 112),
         green=(4278255360, 42), yellow=(4294921216, 26))
# (Name, Algorithmus, Gruppe, Farbe, Beats?, Duration, Properties)
ANIMS = [
    ("Radar", "Circular", 0, "cyan", False, 40, {"circularMode": "Radar", "width": "60", "fadeMode": "Fade Right"}),
    ("Ripple", "Ripple", 0, "blue", False, 50, {}),
    ("Kreisen", "Sinelon", 2, "magenta", False, 30, {}),
    ("Meteor", "Meteor", 2, "white", False, 40, {}),
    ("Jonglieren", "Juggle", 2, "orange", False, 30, {}),
    ("Wellen", "Waves", 0, "cyan", True, 250, {"direction": "Out"}),
    ("Gegenlauf", "Opposite", 3, "purple", True, 500, {}),
    ("Traversen-Wechsel", "Random Row", 3, "white", True, 1000, {}),
    ("Mitte füllen", "Fill Unfill From Center", 0, "orange", True, 1000, {}),
    ("Streifen", "Stripes", 3, "red", True, 500, {}),
    ("Zufall", "Random Single", 2, "pink", True, 500, {}),
    ("Konfetti", "Confetti", 2, "white", False, 50, {"density": "100", "fade": "50"}),
    ("Funkeln", "TwinkleFox", 0, None, False, 40, {}),
    ("Aurora", "Aurora", 0, None, False, 50, {}),
    ("Ozean", "Pacifica", 0, None, False, 50, {}),
    ("Gewitter", "Lightning", 0, "white", False, 30, {}),
]
FIRST_FN, FIRST_WIDGET = 73, 58
funcs = ""
for k, (name, algo, grp, col, beats, dur, props) in enumerate(ANIMS):
    fid = FIRST_FN + k
    tempo = "   <Tempo>Beats</Tempo>\n" if beats else ""
    color = f'   <Color Index="0">{C[col][0]}</Color>\n' if col else ""
    prop = "".join(f'   <Property Name="{n}" Value="{v}"/>\n' for n, v in props.items())
    funcs += (f'  <Function ID="{fid}" Type="RGBMatrix" Name="Bühne – {name}" Path="Effekte/Bühne">\n{tempo}'
              f'   <Speed FadeIn="0" FadeOut="0" Duration="{dur}"/>\n   <Direction>Forward</Direction>\n'
              f'   <RunOrder>Loop</RunOrder>\n   <Algorithm Type="Script">{algo}</Algorithm>\n{color}'
              f'   <ControlMode>RGB</ControlMode>\n   <FixtureGroup>{grp}</FixtureGroup>\n{prop}  </Function>\n')
s = s.replace("  <Monitor ", funcs + "  <Monitor ", 1)

# --- Auto-Programme: alle 24 Effekte
effect_ids = list(range(59, 67)) + [FIRST_FN + k for k in range(len(ANIMS))]
def auto_steps(m):
    head = re.sub(r'   <Step Number=.*?</Step>\n', "", m.group(0))
    steps = "".join(f'   <Step Number="{n}" FadeIn="0" Hold="0" FadeOut="0">{f}</Step>\n'
                    for n, f in enumerate(effect_ids))
    return head.replace("  </Function>\n", steps + "  </Function>\n")
s = re.sub(r'  <Function ID="(6[7-9]|7[0-2])" Type="Chaser" Name="Auto.*?</Function>\n', auto_steps, s, flags=re.S)

# --- 3D-Monitor
# Neigung zur Bühnenmitte, damit die Kegel auf dem Boden landen (QLC+ dreht um -Winkel):
# vorne XRot -, hinten XRot +, rechts ZRot +, links ZRot -
TILT = 10
def rot(ring):
    return [f'XRot="{-TILT}"', f'ZRot="{TILT}"', f'XRot="{TILT}"', f'ZRot="{-TILT}"'][ring // 8]
fx = "".join(f'   <FxItem ID="{fid}" XPos="{pos(r)[0]}" YPos="{pos(r)[1]}" ZPos="{pos(r)[2]}" {rot(r)}/>\n'
             for r, fid in enumerate(ids))
fx += '   <FxItem ID="2" Hidden="True" XPos="0" YPos="1000" ZPos="0"/>\n'
fx += '   <FxItem ID="3" Hidden="True" XPos="350" YPos="1000" ZPos="0"/>\n'
s = re.sub(r"(   <StageItem>2</StageItem>\n)(   <FxItem .*?/>\n)+", lambda m: m.group(1) + fx, s, 1)

# --- Pult: SoloFrame "Bühne" mit 4x4 Tasten, APC-Pads Reihe 3 (Noten 24-31) und Reihe 2 (16-23)
buttons = ""
for k, (name, algo, grp, col, *_ ) in enumerate(ANIMS):
    row, colm = divmod(k, 4)
    note = 24 + k if k < 8 else 16 + (k - 8)
    argb, fb = C[col] if col else (4281348144, 26)
    buttons += f"""    <Button Caption="{name}" ID="{FIRST_WIDGET + k}">
     <WindowState Visible="True" X="{24 + 126 * colm}" Y="{24 + 126 * row}" Width="102" Height="102"/>
     <Appearance>
      <ForegroundColor>4278190080</ForegroundColor>
      <BackgroundColor>{argb}</BackgroundColor>
     </Appearance>
     <Function ID="{FIRST_FN + k}"/>
     <Action>Toggle</Action>
     <Input ID="0" Universe="0" Channel="{128 + note}" LowerValue="{fb}" UpperValue="{fb}" MonitorValue="{fb}" LowerParams="1" UpperParams="9" MonitorParams="9"/>
    </Button>
"""
frame = f"""   <SoloFrame Caption="Bühne" ID="{FIRST_WIDGET + len(ANIMS)}">
    <WindowState Visible="True" X="978" Y="522" Width="528" Height="528"/>
    <AllowResize>True</AllowResize>
    <ShowHeader>False</ShowHeader>
    <ShowEnableButton>True</ShowEnableButton>
    <Collapsed>False</Collapsed>
    <Disabled>False</Disabled>
{buttons}   </SoloFrame>
"""
s = s.replace('   <Frame Caption="Show Wizard" ID="4">', frame + '   <Frame Caption="Show Wizard" ID="4">', 1)

# Auto-Tasten in die unterste APC-Reihe (Noten 0-5)
s = re.sub(r'(<Function ID="(?:6[7-9]|7[0-2])"/>.*?<Input ID="0" Universe="0" Channel=")(15[2-7])"',
           lambda m: f'{m.group(1)}{int(m.group(2)) - 24}"', s, flags=re.S)

open(dst, "w", encoding="utf-8").write(s)
print("ok", len(ids), "Heads,", len(ANIMS), "neue Animationen")
