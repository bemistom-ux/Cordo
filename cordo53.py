import streamlit as st
from music21 import stream, chord, pitch, note, clef, instrument, tempo, expressions
import re

# ---------------------------------------------------------------------------
# CHORD PARSING
# ---------------------------------------------------------------------------

ROOT_PC = {
    'C':0,'C#':1,'Db':1,'D':2,'D#':3,'Eb':3,'E':4,'F':5,
    'F#':6,'Gb':6,'G':7,'G#':8,'Ab':8,'A':9,'A#':10,'Bb':10,'B':11,'Cb':11
}

PREFER_FLATS = {
    'C':False,'C#':False,'Db':True,'D':False,'D#':False,'Eb':True,
    'E':False,'F':True,'F#':False,'Gb':True,'G':False,'G#':False,
    'Ab':True,'A':False,'A#':False,'Bb':True,'B':False,'Cb':True
}

QUALITY_PATTERNS = [
    # minor-major (must come before plain minor and plain major)
    (r'^mMaj7|^mM7|^-M7|^m\(maj7\)',                       3, 11),
    # major 7  —  includes M and ^ shorthands
    (r'^maj13|^maj11|^maj9|^maj7|^M7|^Δ7|^Δ|^maj|\^|^M$', 4, 11),
    # half-diminished  —  includes h shorthand
    (r'^m7b5|^ø7|^ø|^h$',                                  3, 10),
    # fully diminished
    (r'^dim7|^°7|^dim|^°',                                  3,  9),
    # minor 7  —  includes - shorthand (after -M7 already matched above)
    (r'^m13|^m11|^m9|^m7|^min7|^mi7|^-7|^m|^min|^mi|^-$', 3, 10),
    # suspended
    (r'^9sus4|^7sus4|^sus4|^sus2|^sus',                    5, 10),
    # augmented
    (r'^\+7|^aug7',                                        4, 10),
    # dominant 7 and extensions
    (r'^13|^11|^9#11|^9b5|^9|^7#9|^7b9|^7#5|^7b5|^7alt|^7', 4, 10),
    # sixth chords
    (r'^6/9|^69|^6',                                       4,  9),
    # bare root = major 7
    (r'^$',                                                4, 11),
]

def parse_chord(symbol):
    s = symbol.strip()
    m = re.match(r'^([A-G][b#♭♯]?)', s)
    if not m:
        return None
    root_str = m.group(1).replace('♭','b').replace('♯','#')
    if root_str not in ROOT_PC:
        return None
    quality_str = s[m.end():]
    rpc = ROOT_PC[root_str]
    pf  = PREFER_FLATS.get(root_str, False)
    for pattern, t_int, s_int in QUALITY_PATTERNS:
        if re.match(pattern, quality_str):
            # Minor, half-dim and dim chords always prefer flat spellings
            # regardless of root (Gm uses Bb not A#, etc.)
            if t_int == 3:   # minor third = minor quality
                pf = True
            return root_str, (rpc + t_int) % 12, (rpc + s_int) % 12, pf
    return None


# ---------------------------------------------------------------------------
# VOICING
# ---------------------------------------------------------------------------

def all_midis_for_pc(pc, low=48, high=76):
    return [(oct + 1) * 12 + pc for oct in range(2, 8)
            if low <= (oct + 1) * 12 + pc <= high]

def has_common_tone(voicing, prev_midis):
    if not prev_midis:
        return False
    prev_pcs = {p % 12 for p in prev_midis}
    return any(v % 12 in prev_pcs for v in voicing)

def total_motion(voicing, prev_midis):
    if not prev_midis:
        return 0
    return sum(min(abs(v - p) for p in prev_midis) for v in voicing)

def get_voicing(tpc, spc, prev, reg=60, mode='Mixed'):
    cands = [tuple(sorted([t,s])) for t in all_midis_for_pc(tpc, reg-14, reg+14)
             for s in all_midis_for_pc(spc, reg-14, reg+14)
             if t != s and 1 <= abs(t-s) <= 15]
    if not cands:
        cands = [tuple(sorted([t,s])) for t in all_midis_for_pc(tpc)
                 for s in all_midis_for_pc(spc)
                 if t != s and 1 <= abs(t-s) <= 15]
    if not cands:
        return None, None

    if mode == '3-7':
        # Third on bottom, seventh on top — pick octave closest to reg
        cands = [c for c in cands if c[0] % 12 == tpc % 12]  # low note = third
        if not cands: return None, None
        best = min(cands, key=lambda c: abs(sum(c)/len(c) - reg))
    elif mode == '7-3':
        # Seventh on bottom, third on top — pick octave closest to reg
        cands = [c for c in cands if c[0] % 12 == spc % 12]  # low note = seventh
        if not cands: return None, None
        best = min(cands, key=lambda c: abs(sum(c)/len(c) - reg))
    else:
        # Mixed — voice leading picks best inversion
        if prev:
            common = [c for c in cands if has_common_tone(c, prev)]
            pool   = common if common else cands
            def score(c):
                tot = total_motion(c, prev)
                max_jump = max(min(abs(x-p) for p in prev) for x in c)
                return (max_jump > 7, tot, max_jump)
            best = min(pool, key=score)
        else:
            best = min(cands, key=lambda c: abs(sum(c)/len(c) - reg))

    return best, None


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

# Explicit spelling tables using music21's naming (- = flat)
_PITCH_FLAT  = ['C','D-','D','E-','E','F','G-','G','A-','A','B-','C-']
_PITCH_SHARP = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']

def midi_to_pitch_obj(midi_val, prefer_flats):
    pc  = midi_val % 12
    oct = midi_val // 12 - 1
    if prefer_flats and pc == 11:   # B -> Cb in next octave
        return pitch.Pitch('C-' + str(oct + 1))
    name = (_PITCH_FLAT if prefer_flats else _PITCH_SHARP)[pc]
    return pitch.Pitch(name + str(oct))

def best_bass_midi(pc, low=28, high=52):
    best, bd = None, 999
    target = 38
    for oct in range(1, 6):
        m = (oct + 1) * 12 + pc
        if low <= m <= high and abs(m - target) < bd:
            bd = abs(m - target)
            best = m
    return best


# ---------------------------------------------------------------------------
# SCORE GENERATION
# ---------------------------------------------------------------------------

REG_RH = 62   # right hand: around D4
REG_LH = 50   # left hand: around D3 — sits on the bass clef staff comfortably

def generate_files(chord_list, bpm, hand_choice, b_style, voicing_mode='Mixed'):
    xml_score  = stream.Score()
    midi_score = stream.Score()

    is_lh = "Left" in hand_choice
    reg   = REG_LH if is_lh else REG_RH

    piano_clef = clef.BassClef() if is_lh else clef.TrebleClef()
    p_xml = stream.Part(id='Piano');  p_xml.insert(0, instrument.Piano()); p_xml.insert(0, piano_clef)
    b_xml = stream.Part(id='Bass');   b_xml.insert(0, instrument.AcousticBass())
    d_xml = stream.Part(id='Drums');  d_xml.insert(0, instrument.Percussion())
    b_mid = stream.Part(id='BM');     b_mid.insert(0, instrument.ElectricBass())
    d_mid = stream.Part(id='DM');     d_mid.insert(0, instrument.Percussion())

    tm = tempo.MetronomeMark(number=bpm)

    # Measure 0
    for p in [p_xml, b_xml]:
        m0 = stream.Measure(number=0)
        if p == p_xml:
            m0.insert(0, clef.BassClef() if is_lh else clef.TrebleClef())
        elif p == b_xml:
            m0.insert(0, clef.BassClef())
        m0.append(note.Rest(type='whole'))
        p.append(m0)

    # Drum count-in — use a separate percussion part, never mixed with piano
    m0d = stream.Measure(number=0)
    m0d.insert(0, clef.PercussionClef())
    m0d.insert(0, tm)
    for _ in range(4):
        m0d.append(note.Note(44, quarterLength=1.0))
    d_xml.append(m0d)

    m0dm = stream.Measure(number=0)
    m0dm.insert(0, tm)
    for _ in range(4):
        m0dm.append(note.Note(44, quarterLength=1.0))
    d_mid.append(m0dm)

    m0bm = stream.Measure(number=0)
    m0bm.append(note.Rest(type='whole'))
    b_mid.append(m0bm)

    prev_midis = None
    skipped    = []

    for i, raw in enumerate(chord_list):
        parsed = parse_chord(raw)

        if parsed is None:
            skipped.append(raw)
            for p in [p_xml, b_xml]:
                rm = stream.Measure(number=i + 1)
                rm.append(note.Rest(type='whole'))
                p.append(rm)
            for p in [d_xml, d_mid]:
                dm = stream.Measure(number=i + 1)
                for _ in range(4):
                    dm.append(note.Note(44, quarterLength=1.0))
                p.append(dm)
            bm = stream.Measure(number=i + 1)
            bm.append(note.Rest(type='whole'))
            b_mid.append(bm)
            continue

        root_str, tpc, spc, pf = parsed
        voicing, _ = get_voicing(tpc, spc, prev_midis, reg, voicing_mode)

        if voicing is None:
            skipped.append(raw)
            continue

        low_p  = midi_to_pitch_obj(voicing[0], pf)
        high_p = midi_to_pitch_obj(voicing[1], pf)

        # Piano
        pm = stream.Measure(number=i + 1)
        pm.append(expressions.TextExpression(raw))
        pm.append(chord.Chord([low_p, high_p], quarterLength=4.0))
        p_xml.append(pm)

        # Bass
        rpc_val = ROOT_PC[root_str]
        br      = best_bass_midi(rpc_val)
        bass_p  = midi_to_pitch_obj(br, pf)

        bm_xml = stream.Measure(number=i + 1)
        bm_xml.append(note.Note(bass_p, type='whole'))
        b_xml.append(bm_xml)

        # Drums XML — ride on all 4 beats
        dm_xml = stream.Measure(number=i + 1)
        for _ in range(4):
            dm_xml.append(note.Note(51, quarterLength=1.0))
        d_xml.append(dm_xml)

        # MIDI bass
        bm_mid = stream.Measure(number=i + 1)
        pat = [br, br + 7, br + 12, br + 7] if "Classic" in b_style else [br] * 4
        for mv in pat:
            bm_mid.append(note.Note(mv, type='quarter'))
        b_mid.append(bm_mid)

        # MIDI drums
        dm_mid = stream.Measure(number=i + 1)
        for _ in range(4):
            dm_mid.append(note.Note(51, type='quarter'))
        d_mid.append(dm_mid)

        prev_midis = list(voicing)

    xml_score.insert(0, p_xml)
    xml_score.insert(0, b_xml)
    xml_score.insert(0, d_xml)
    midi_score.insert(0, b_mid)
    midi_score.insert(0, d_mid)

    for n in b_mid.recurse().notes: n.channel = 2
    for n in d_mid.recurse().notes: n.channel = 10

    return xml_score, midi_score, skipped


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Jazz Guide Tones", layout="wide")
st.title("🎹 Jazz Guide Tone Practice Sheet")

if 'xml' not in st.session_state: st.session_state.xml = None
if 'mid' not in st.session_state: st.session_state.mid = None

with st.sidebar:
    hand         = st.radio("Clef", ["Left Hand (Bass Clef)", "Right Hand (Treble)"])
    voicing_mode = st.radio("Voicing", ["Mixed", "3-7", "7-3"])
    b_style      = st.selectbox("Bass Style", ["Root Only", "Classic 1-5"])
    bpm          = st.slider("BPM", 40, 200, 110)

st.caption(
    "Enter chords separated by spaces or line breaks. "
    "Shorthands: M or ^ = maj7, - = m7, h = half-dim. "
    "e.g. EbM, Eb^, Bb-, Bh"
)

score_name = st.text_input("Score name (used for filenames):", "my_changes")

user_prog = st.text_area(
    "Chord progression:",
    "Dm7 G7 Cmaj7 Cmaj7\nAm7 D7 Gmaj7 Gmaj7"
)

if st.button("Generate Score"):
    chord_list = user_prog.split()
    # Sanitise name for use in filenames
    safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', score_name.strip()) or "my_changes"
    if chord_list:
        with st.spinner("Building score…"):
            xml_obj, mid_obj, skipped = generate_files(
                chord_list, bpm, hand, b_style, voicing_mode
            )
        if skipped:
            st.warning(f"Couldn't parse: {', '.join(skipped)} — rests inserted.")

        xp = f"{safe_name}.musicxml"
        xml_obj.write('musicxml', fp=xp)
        with open(xp, "rb") as f:
            st.session_state.xml = f.read()

        mp = f"{safe_name}.mid"
        mid_obj.write('midi', fp=mp)
        with open(mp, "rb") as f:
            st.session_state.mid = f.read()

        st.session_state.safe_name = safe_name
        st.success("Done! Download your files below.")

st.divider()
c1, c2 = st.columns(2)
safe = st.session_state.get('safe_name', 'jazz_guide_tones')
if st.session_state.mid:
    c1.download_button("🎵 MIDI",  st.session_state.mid, f"{safe}.mid")
if st.session_state.xml:
    c2.download_button("💾 Score", st.session_state.xml, f"{safe}.musicxml")

