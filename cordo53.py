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

# (pattern, third, seventh, fifth, ninth, quality_name, extensions)
# extensions = list of semitone intervals above root to include in Full Chord
# Basic chords (maj7/m7/7) get just R+3+5+7 = []
# Extended chords add intervals explicitly written in the symbol
QUALITY_PATTERNS = [
    # minor-major
    (r'^mMaj7|^mM7|^-M7|^m\(maj7\)',   3, 11,  7, 14, 'mMaj7', []),
    # major extensions
    (r'^maj13',                          4, 11,  7, 14, 'maj13', [14, 21]),
    (r'^maj11',                          4, 11,  7, 14, 'maj11', [14, 17]),
    (r'^maj9',                           4, 11,  7, 14, 'maj9',  [14]),
    (r'^maj7|^M7|^Δ7|^Δ|^maj|\^|^M$',   4, 11,  7, 14, 'maj7',  []),
    # half-dim / dim
    (r'^m7b5|^ø7|^ø|^h$',               3, 10,  6, 14, 'm7b5',  []),
    (r'^dim7|^°7|^dim|^°',               3,  9,  6, 14, 'dim7',  []),
    # minor extensions
    (r'^m13',                            3, 10,  7, 14, 'm13',   [14, 21]),
    (r'^m11',                            3, 10,  7, 14, 'm11',   [14, 17]),
    (r'^m9',                             3, 10,  7, 14, 'm9',    [14]),
    (r'^m7|^min7|^mi7|^-7|^m|^min|^mi|^-$', 3, 10, 7, 14, 'm7', []),
    # suspended
    (r'^9sus4|^7sus4|^sus4|^sus2|^sus',  5, 10,  7, 14, 'sus',   []),
    # augmented
    (r'^\+7|^aug7',                      4, 10,  8, 14, 'aug7',  []),
    # dominant extensions — plain
    (r'^13',                             4, 10,  7, 14, 'dom13', [14, 21]),
    (r'^11',                             4, 10,  7, 14, 'dom11', [14, 17]),
    (r'^9#11',                           4, 10,  7, 14, 'dom9#11',[14, 18]),
    (r'^9b5',                            4, 10,  6, 14, 'dom9b5', [14]),
    (r'^9',                              4, 10,  7, 14, 'dom9',  [14]),
    # altered dominants — each with its correct ninth
    (r'^7b9',                            4, 10,  7, 13, 'dom7b9', [13]),   # b9 = 13 semitones
    (r'^7#9',                            4, 10,  7, 15, 'dom7#9', [15]),   # #9 = 15 semitones
    (r'^7alt',                           4, 10,  7, 13, 'dom7alt',[13, 15]),  # b9 + #9
    (r'^7#11',                           4, 10,  7, 14, 'dom7#11',[14, 18]), # natural 9 + #11
    (r'^7b5',                            4, 10,  6, 14, 'dom7b5', []),
    (r'^7#5',                            4, 10,  8, 14, 'dom7#5', []),
    (r'^7',                              4, 10,  7, 14, 'dom7',   []),
    # sixth chords
    (r'^6/9|^69',                        4,  9,  7, 14, 'maj69', [14]),
    (r'^6',                              4,  9,  7, 14, 'maj6',  []),
    # bare root = major 7
    (r'^$',                              4, 11,  7, 14, 'maj7',  []),
]

def parse_chord(symbol):
    """Returns (root_str, third_pc, seventh_pc, fifth_pc, ninth_pc, prefer_flats, extensions)
       or None. extensions is a list of semitone intervals above root for Full Chord."""
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
    for pattern, t, sv, fi, ni, _, exts in QUALITY_PATTERNS:
        if re.match(pattern, quality_str):
            if t == 3:
                pf = True
            return (root_str,
                    (rpc + t)  % 12,
                    (rpc + sv) % 12,
                    (rpc + fi) % 12,
                    (rpc + ni) % 12,
                    pf,
                    [(rpc + e) % 12 for e in exts])
    return None


# ---------------------------------------------------------------------------
# PITCH SPELLING
# ---------------------------------------------------------------------------

_FLAT  = ['C','D-','D','E-','E','F','G-','G','A-','A','B-','C-']
_SHARP = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']

def midi_to_pitch_obj(midi_val, pf):
    pc  = midi_val % 12
    oct = midi_val // 12 - 1
    if pf and pc == 11:
        return pitch.Pitch('C-' + str(oct + 1))
    name = (_FLAT if pf else _SHARP)[pc]
    return pitch.Pitch(name + str(oct))


# ---------------------------------------------------------------------------
# COLORS
# ---------------------------------------------------------------------------

COLOR_ROOT    = '#000000'   # black
COLOR_GUIDE   = '#0066CC'   # blue  (both 3+7 in highlight mode)
COLOR_THIRD   = '#0066CC'   # blue
COLOR_SEVENTH = '#007700'   # green
COLOR_FIFTH   = '#888888'   # gray
COLOR_NINTH   = '#CC0000'   # red
COLOR_EXT     = '#7700CC'   # purple  (11ths, 13ths)

def color_for_role(role, color_mode):
    if role == 'root':      return COLOR_ROOT
    if role == 'fifth':     return COLOR_FIFTH
    if role == 'ninth':     return COLOR_NINTH
    if role == 'extension': return COLOR_EXT
    # third or seventh
    if color_mode == 'Highlight 3+7':
        return COLOR_GUIDE
    return COLOR_THIRD if role == 'third' else COLOR_SEVENTH


# ---------------------------------------------------------------------------
# REGISTER HELPERS
# ---------------------------------------------------------------------------

def all_midis_for_pc(pc, low=36, high=84):
    return [(o+1)*12+pc for o in range(2,8) if low <= (o+1)*12+pc <= high]

def closest_midi(pc, target, low=36, high=84):
    opts = all_midis_for_pc(pc, low, high)
    return min(opts, key=lambda m: abs(m-target)) if opts else None

def best_bass_midi(pc):
    return closest_midi(pc, 38, 28, 52)


# ---------------------------------------------------------------------------
# VOICING BUILDERS
# ---------------------------------------------------------------------------

def has_common_tone(v, prev):
    if not prev: return False
    pp = {p % 12 for p in prev}
    return any(x % 12 in pp for x in v)

def total_motion(v, prev):
    if not prev: return 0
    return sum(min(abs(x-p) for p in prev) for x in v)


def build_guide_tones(tpc, spc, prev, reg, vmode):
    """Returns (low_midi, high_midi) or None."""
    cands = [tuple(sorted([t,s]))
             for t in all_midis_for_pc(tpc, reg-14, reg+14)
             for s in all_midis_for_pc(spc, reg-14, reg+14)
             if t != s and 1 <= abs(t-s) <= 15]
    if not cands:
        cands = [tuple(sorted([t,s]))
                 for t in all_midis_for_pc(tpc)
                 for s in all_midis_for_pc(spc)
                 if t != s and 1 <= abs(t-s) <= 15]
    if not cands:
        return None

    if vmode == '3-7':
        cands = [c for c in cands if c[0] % 12 == tpc % 12] or cands
        return min(cands, key=lambda c: abs(sum(c)/2 - reg))
    elif vmode == '7-3':
        cands = [c for c in cands if c[0] % 12 == spc % 12] or cands
        return min(cands, key=lambda c: abs(sum(c)/2 - reg))
    else:
        if prev:
            pool = [c for c in cands if has_common_tone(c, prev)] or cands
            def score(c):
                tot   = total_motion(c, prev)
                mx    = max(min(abs(x-p) for p in prev) for x in c)
                drift = abs(sum(c)/len(c) - reg)
                return (mx > 7, tot + drift * 2.0, mx)
            return min(pool, key=score)
        return min(cands, key=lambda c: abs(sum(c)/2 - reg))


def build_rootless(tpc, spc, npc, reg, prev=None):
    """
    Rootless voicing: 7, 3, 9 — no 5th.
    Tries all inversions and picks best via voice leading.
    """
    low  = reg - 14
    high = reg + 14
    t_opts = all_midis_for_pc(tpc, low, high)
    s_opts = all_midis_for_pc(spc, low, high)
    n_opts = all_midis_for_pc(npc, low, high)

    if not t_opts or not s_opts or not n_opts:
        return None

    # All valid 3-note voicings: span <= 18 semitones, all distinct
    candidates = []
    for t in t_opts:
        for s in s_opts:
            for n in n_opts:
                v = tuple(sorted([t, s, n]))
                if len(set(v)) == 3 and v[-1] - v[0] <= 18:
                    candidates.append(v)

    if not candidates:
        return None

    if prev:
        common = [c for c in candidates if has_common_tone(c, prev)]
        pool   = common if common else candidates
        def score(c):
            tot   = total_motion(c, prev)
            mx    = max(min(abs(x-p) for p in prev) for x in c)
            drift = abs(sum(c)/len(c) - reg)
            return (mx > 7, tot + drift * 2.0, mx)
        return list(min(pool, key=score))
    else:
        return list(min(candidates, key=lambda c: abs(sum(c)/len(c) - reg)))


def build_full_chord(rpc, tpc, spc, npc, extensions, reg, prev=None):
    """
    Full chord = R + 3 + 7 + any extensions (no 5th).
    Tries all inversions and picks best via voice leading.
    """
    ro = closest_midi(rpc, reg - 7)
    if ro is None: return None, []

    # Core: root, third, seventh (no fifth)
    core_pcs   = [rpc, tpc, spc]
    core_roles = ['root', 'third', 'seventh']
    ext_roles  = ['ninth'] + ['extension'] * (len(extensions) - 1)

    all_pcs   = core_pcs   + extensions
    all_roles = core_roles + ext_roles

    # Stack upward from root
    midi_notes = [ro]
    role_list  = ['root']
    prev_note  = ro

    for pc, role in zip(all_pcs[1:], all_roles[1:]):
        nxt = closest_midi(pc, prev_note + 6, prev_note + 1, prev_note + 19)
        if nxt is None:
            opts = [m for m in all_midis_for_pc(pc) if m > prev_note]
            if not opts: continue
            nxt = min(opts)
        midi_notes.append(nxt)
        role_list.append(role)
        prev_note = nxt

    if len(midi_notes) < 2:
        return None, []
    if midi_notes[-1] - midi_notes[0] > 26:
        return None, []

    # Try all inversions
    n = len(midi_notes)
    sorted_pairs = sorted(zip(midi_notes, role_list))
    base_midis = [x[0] for x in sorted_pairs]
    base_roles = [x[1] for x in sorted_pairs]

    inversions = []
    for i in range(n):
        inv = list(base_midis)
        inv_roles = list(base_roles)
        for j in range(i):
            inv[j] += 12
        inv_sorted = sorted(zip(inv, inv_roles))
        inv_midis = [x[0] for x in inv_sorted]
        inv_roles2 = [x[1] for x in inv_sorted]
        if inv_midis[-1] - inv_midis[0] <= 26:
            inversions.append((inv_midis, inv_roles2))

    if not inversions:
        return sorted(midi_notes), base_roles

    if prev:
        common = [(m, r) for m, r in inversions if has_common_tone(m, prev)]
        pool   = common if common else inversions
        def score(mr):
            m     = mr[0]
            tot   = total_motion(m, prev)
            mx    = max(min(abs(x-p) for p in prev) for x in m)
            drift = abs(sum(m)/len(m) - reg)
            return (mx > 7, tot + drift * 2.0, mx)
        best_midis, best_roles = min(pool, key=score)
    else:
        best_midis, best_roles = min(inversions,
            key=lambda mr: abs(sum(mr[0])/len(mr[0]) - reg))

    return best_midis, best_roles


def make_chord(midi_list, role_map, pf, color_mode, duration=4.0):
    """Build a colored music21 Chord from midi values and a pc→role map."""
    notes = []
    for m in midi_list:
        p = midi_to_pitch_obj(m, pf)
        role = role_map.get(m % 12, 'fifth')
        n = note.Note()
        n.pitch = p
        n.style.color = color_for_role(role, color_mode)
        notes.append(n)
    return chord.Chord(notes, quarterLength=duration)



# ---------------------------------------------------------------------------
# RHYTHM PATTERNS
# ---------------------------------------------------------------------------

def make_chord_rhythm(piano_chord, rhythm):
    """
    Returns a list of music21 elements (notes/rests) for one measure
    of the given chord in the specified rhythm pattern.

    rhythm options:
      'Whole note'     — one whole note
      'Beats 2 & 4'   — rests on 1&3, chords on 2&4
      'Charleston'     — chord on beat 1, chord on and-of-2
      'Two feel'       — half notes on beats 1 and 3
    """
    def ch(ql):
        # Clone the chord with a new duration
        c = chord.Chord([n.pitch for n in piano_chord.notes], quarterLength=ql)
        for i, n in enumerate(c.notes):
            n.style.color = piano_chord.notes[i].style.color
        return c

    if rhythm == 'Beats 2 & 4':
        return [
            note.Rest(quarterLength=1.0),
            ch(1.0),
            note.Rest(quarterLength=1.0),
            ch(1.0),
        ]
    elif rhythm == 'Charleston':
        # Beat 1 (quarter) + rest (eighth) + chord on and-of-2 (dotted quarter carries to 4)
        return [
            ch(1.0),
            note.Rest(quarterLength=0.5),
            ch(1.5),
            note.Rest(quarterLength=1.0),
        ]
    elif rhythm == 'Two feel':
        return [
            ch(2.0),
            ch(2.0),
        ]
    else:  # Whole note
        return [ch(4.0)]


def make_bass_rhythm(bass_p, br, b_style, rhythm):
    """
    Returns a list of music21 elements for the bass in one measure.
    bass_p  = music21 Pitch for root
    br      = root MIDI number
    b_style = 'Root Only' or 'Classic 1-5'
    rhythm  = same rhythm string as above
    """
    fifth_p = midi_to_pitch_obj(br + 7, False)

    def root_note(ql):
        return note.Note(bass_p, quarterLength=ql)

    def fifth_note(ql):
        n = note.Note()
        n.pitch = fifth_p
        n.quarterLength = ql
        return n

    if b_style == 'Classic 1-5':
        if rhythm == 'Whole note':
            return [root_note(2.0), fifth_note(2.0)]
        elif rhythm == 'Beats 2 & 4':
            return [note.Rest(quarterLength=1.0), root_note(1.0),
                    note.Rest(quarterLength=1.0), fifth_note(1.0)]
        elif rhythm == 'Charleston':
            return [root_note(1.0), note.Rest(quarterLength=0.5),
                    fifth_note(1.5), note.Rest(quarterLength=1.0)]
        elif rhythm == 'Two feel':
            return [root_note(2.0), fifth_note(2.0)]
    else:  # Root Only
        if rhythm == 'Whole note':
            return [root_note(4.0)]
        elif rhythm == 'Beats 2 & 4':
            return [note.Rest(quarterLength=1.0), root_note(1.0),
                    note.Rest(quarterLength=1.0), root_note(1.0)]
        elif rhythm == 'Charleston':
            return [root_note(1.0), note.Rest(quarterLength=0.5),
                    root_note(1.5), note.Rest(quarterLength=1.0)]
        elif rhythm == 'Two feel':
            return [root_note(2.0), root_note(2.0)]

    return [root_note(4.0)]  # fallback




REG_RH = 62
REG_LH = 50

def generate_files(chord_list, bpm, hand_choice, b_style,
                   note_mode, voicing_mode, n_notes, color_mode,
                   score_title='Jazz Guide Tones', rhythm='Whole note'):

    xml_score  = stream.Score()
    midi_score = stream.Score()

    is_lh      = "Left" in hand_choice
    reg        = REG_LH if is_lh else REG_RH
    piano_clef = clef.BassClef() if is_lh else clef.TrebleClef()

    p_xml = stream.Part(id='Piano')
    p_xml.insert(0, instrument.Piano())
    p_xml.insert(0, piano_clef)

    b_xml = stream.Part(id='Bass');  b_xml.insert(0, instrument.AcousticBass())
    b_xml.insert(0, clef.BassClef())
    d_xml = stream.Part(id='Drums'); d_xml.insert(0, instrument.Percussion())
    b_mid = stream.Part(id='BM');    b_mid.insert(0, instrument.ElectricBass())
    d_mid = stream.Part(id='DM');    d_mid.insert(0, instrument.Percussion())

    from music21 import metadata as md
    xml_score.metadata = md.Metadata()
    xml_score.metadata.title = score_title

    # Settings summary shown top-right (composer field)
    clef_label    = "Left Hand" if is_lh else "Right Hand"
    if note_mode == 'Guide Tones':
        mode_label = f"Guide Tones | {voicing_mode}"
    elif note_mode == 'Rootless':
        mode_label = "Rootless (7-3-9)"
    else:
        mode_label = "Full Chord"
    color_label = "Highlight 3+7" if color_mode == 'Highlight 3+7' else "Each interval"
    xml_score.metadata.composer = f"{clef_label} | {mode_label} | {color_label} | {rhythm}"

    # Color legend as subtitle
    if note_mode == 'Guide Tones':
        if color_mode == 'Highlight 3+7':
            legend_str = "3rd & 7th = BLUE"
        else:
            legend_str = "3rd = BLUE   |   7th = GREEN"
    elif note_mode == 'Rootless':
        if color_mode == 'Highlight 3+7':
            legend_str = "3rd & 7th = BLUE   |   9th = RED"
        else:
            legend_str = "3rd = BLUE   |   7th = GREEN   |   9th = RED"
    else:
        if color_mode == 'Highlight 3+7':
            legend_str = "Root = BLACK   |   3rd & 7th = BLUE   |   9th = RED   |   extensions = PURPLE"
        else:
            legend_str = "Root = BLACK   |   3rd = BLUE   |   7th = GREEN   |   9th = RED   |   extensions = PURPLE"
    xml_score.metadata.subtitle = legend_str

    tm = tempo.MetronomeMark(number=bpm)

    # Measure 0
    m0p = stream.Measure(number=0)
    m0p.insert(0, clef.BassClef() if is_lh else clef.TrebleClef())
    m0p.append(note.Rest(type='whole'))
    p_xml.append(m0p)

    m0b = stream.Measure(number=0)
    m0b.insert(0, clef.BassClef())
    m0b.append(note.Rest(type='whole'))
    b_xml.append(m0b)

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

    def rest_measure(num):
        for p in [p_xml, b_xml]:
            rm = stream.Measure(number=num)
            rm.append(note.Rest(type='whole'))
            p.append(rm)
        for p in [d_xml, d_mid]:
            dm = stream.Measure(number=num)
            for _ in range(4):
                dm.append(note.Note(44, quarterLength=1.0))
            p.append(dm)
        b_mid.append(stream.Measure(number=num,
                     elements=[note.Rest(type='whole')]))

    for i, raw in enumerate(chord_list):
        parsed = parse_chord(raw)
        if parsed is None:
            skipped.append(raw)
            rest_measure(i+1)
            continue

        root_str, tpc, spc, fpc, npc, pf, extensions = parsed
        rpc = ROOT_PC[root_str]

        # Build voicing
        midi_notes = None
        role_map   = {}

        if note_mode == 'Guide Tones':
            gt = build_guide_tones(tpc, spc, prev_midis, reg, voicing_mode)
            if gt is not None:
                midi_notes = list(gt)
                role_map   = {tpc: 'third', spc: 'seventh'}

        elif note_mode == 'Rootless':
            rl = build_rootless(tpc, spc, npc, reg, prev_midis)
            if rl is not None:
                midi_notes = rl
                role_map   = {tpc: 'third', spc: 'seventh', npc: 'ninth'}

        else:  # Full Chord
            fc, fc_roles = build_full_chord(rpc, tpc, spc, npc, extensions, reg, prev_midis)
            if fc is not None:
                midi_notes = fc
                # build role_map from the returned role list
                role_map = {}
                for midi_val, role in zip(fc, fc_roles):
                    role_map[midi_val % 12] = role

        if midi_notes is None:
            skipped.append(raw)
            rest_measure(i+1)
            continue

        piano_chord = make_chord(midi_notes, role_map, pf, color_mode)
        prev_midis  = midi_notes

        # Piano — apply rhythm pattern
        pm = stream.Measure(number=i+1)
        pm.append(expressions.TextExpression(raw))
        for elem in make_chord_rhythm(piano_chord, rhythm):
            pm.append(elem)
        p_xml.append(pm)

        # Bass — apply rhythm pattern
        br     = best_bass_midi(rpc)
        bass_p = midi_to_pitch_obj(br, pf)
        bm_xml = stream.Measure(number=i+1)
        for elem in make_bass_rhythm(bass_p, br, b_style, rhythm):
            bm_xml.append(elem)
        b_xml.append(bm_xml)

        # Drums
        dm_xml = stream.Measure(number=i+1)
        for _ in range(4):
            dm_xml.append(note.Note(51, quarterLength=1.0))
        d_xml.append(dm_xml)

        # MIDI bass
        bm_mid = stream.Measure(number=i+1)
        pat = [br, br+7, br+12, br+7] if "Classic" in b_style else [br]*4
        for mv in pat:
            bm_mid.append(note.Note(mv, type='quarter'))
        b_mid.append(bm_mid)

        # MIDI drums
        dm_mid = stream.Measure(number=i+1)
        for _ in range(4):
            dm_mid.append(note.Note(51, type='quarter'))
        d_mid.append(dm_mid)

    xml_score.insert(0, p_xml)
    xml_score.insert(0, b_xml)
    xml_score.insert(0, d_xml)
    midi_score.insert(0, b_mid)
    midi_score.insert(0, d_mid)

    for n in b_mid.recurse().notes: n.channel = 2
    for n in d_mid.recurse().notes: n.channel = 10

    return xml_score, midi_score, skipped



# ---------------------------------------------------------------------------
# PROGRESSION BUILDER DATA
# ---------------------------------------------------------------------------

KEY_ORDER = ['C','Db','D','Eb','E','F','Gb','G','Ab','A','Bb','B']

KEY_NOTES = {
    'C':  ['C','Db','D','Eb','E','F','F#','G','Ab','A','Bb','B'],
    'Db': ['Db','D','Eb','E','F','Gb','G','Ab','A','Bb','B','C'],
    'D':  ['D','Eb','E','F','F#','G','Ab','A','Bb','B','C','Db'],
    'Eb': ['Eb','E','F','Gb','G','Ab','A','Bb','B','C','Db','D'],
    'E':  ['E','F','F#','G','G#','A','Bb','B','C','C#','D','Eb'],
    'F':  ['F','Gb','G','Ab','A','Bb','B','C','Db','D','Eb','E'],
    'Gb': ['Gb','G','Ab','A','Bb','B','C','Db','D','Eb','E','F'],
    'G':  ['G','Ab','A','Bb','B','C','Db','D','Eb','E','F','F#'],
    'Ab': ['Ab','A','Bb','B','C','Db','D','Eb','E','F','Gb','G'],
    'A':  ['A','Bb','B','C','C#','D','Eb','E','F','F#','G','Ab'],
    'Bb': ['Bb','B','C','Db','D','Eb','E','F','Gb','G','Ab','A'],
    'B':  ['B','C','C#','D','D#','E','F','F#','G','G#','A','Bb'],
}

# (name, description, list of (semitones, quality))
PROGRESSIONS = [
    ("ii-V-I  (Bebop)",
     "Dominant b9 — classic bebop tension",
     [(2,'m7'),(7,'7b9'),(0,'maj7'),(0,'maj7')]),

    ("ii-V-I  (Modern/Altered)",
     "Altered dominant — contemporary sound",
     [(2,'m7'),(7,'7alt'),(0,'maj7'),(0,'maj7')]),

    ("ii-V-i  (Minor)",
     "Half-dim and b9 resolving to minor",
     [(2,'m7b5'),(7,'7b9'),(0,'m7'),(0,'m7')]),

    ("ii-V-I",
     "Backbone of jazz",
     [(2,'m7'),(7,'7'),(0,'maj7'),(0,'maj7')]),

    ("I-VI-ii-V  (Turnaround)",
     "Loops back to top",
     [(0,'maj7'),(9,'m7'),(2,'m7'),(7,'7')]),

    ("iii-VI-ii-V",
     "Turnaround variant",
     [(4,'m7'),(9,'7'),(2,'m7'),(7,'7')]),

    ("I-IV-ii-V",
     "Diatonic through IV",
     [(0,'maj7'),(5,'maj7'),(2,'m7'),(7,'7')]),

    ("Blues  (12 bars)",
     "All dominant 7s",
     [(0,'7'),(0,'7'),(0,'7'),(0,'7'),
      (5,'7'),(5,'7'),(0,'7'),(0,'7'),
      (2,'m7'),(7,'7'),(0,'7'),(7,'7')]),

    ("Minor Blues  (12 bars)",
     "Minor key blues",
     [(0,'m7'),(0,'m7'),(0,'m7'),(0,'m7'),
      (5,'m7'),(5,'m7'),(0,'m7'),(0,'m7'),
      (2,'m7b5'),(7,'7b9'),(0,'m7'),(7,'7b9')]),

    ("Rhythm Changes A  (8 bars)",
     "I Got Rhythm A section",
     [(0,'maj7'),(7,'7'),(2,'m7'),(7,'7'),
      (0,'maj7'),(7,'7'),(2,'m7'),(7,'7')]),

    ("Rhythm Changes Bridge  (8 bars)",
     "Dominant 7 cycle",
     [(2,'7'),(2,'7'),(7,'7'),(7,'7'),
      (5,'7'),(5,'7'),(7,'7'),(7,'7')]),

    ("Minor ii-V-i",
     "Half-dim and dominant b9",
     [(2,'m7b5'),(7,'7b9'),(0,'m7'),(0,'m7')]),

    ("Coltrane Changes",
     "Giant Steps — major thirds",
     [(0,'maj7'),(4,'7'),(8,'maj7'),(0,'7'),
      (5,'maj7'),(9,'7'),(0,'maj7'),(0,'maj7')]),

    ("Modal Vamp",
     "One or two chords",
     [(0,'m7'),(0,'m7'),(2,'m7'),(2,'m7')]),

    ("Descending ii-Vs",
     "Chain of ii-Vs down by steps",
     [(2,'m7'),(7,'7'),(0,'m7'),(5,'7'),
      (10,'m7'),(3,'7'),(8,'maj7'),(8,'maj7')]),

    ("Bird Blues  (12 bars)",
     "Parker blues with subs",
     [(0,'7'),(5,'7'),(0,'7'),(2,'m7'),
      (5,'7'),(5,'7'),(0,'7'),(2,'m7'),
      (2,'m7'),(7,'7'),(0,'7'),(2,'m7')]),

    ("I-ii-iii-IV  (Diatonic)",
     "Ascending diatonic",
     [(0,'maj7'),(2,'m7'),(4,'m7'),(5,'maj7')]),
]

def transpose_progression(chords, key):
    """Transpose a list of (semitones, quality) to chord symbols in the given key."""
    notes = KEY_NOTES[key]
    return [notes[semitones] + quality for semitones, quality in chords]


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Jazz Guide Tones", layout="wide")
st.title("🎹 Jazz Guide Tone Practice Sheet")

for key in ['xml', 'mid', 'safe_name']:
    if key not in st.session_state:
        st.session_state[key] = None if key != 'safe_name' else 'jazz_guide_tones'

with st.sidebar:
    hand      = st.radio("Clef",      ["Left Hand (Bass Clef)", "Right Hand (Treble)"])
    note_mode = st.radio("Notes",     ["Guide Tones", "Rootless", "Full Chord"])
    color_mode= st.radio("Colors",    ["Highlight 3+7", "Each interval"])

    if note_mode == 'Guide Tones':
        voicing_mode = st.radio("Voicing", ["Mixed", "3-7", "7-3"])
        n_notes = 2
    elif note_mode == 'Rootless':
        voicing_mode = 'Mixed'
        n_notes = 3  # always 3 now (7-3-9)
    else:
        voicing_mode = 'Mixed'
        n_notes = 4  # unused

    b_style = st.selectbox("Bass Style", ["Root Only", "Classic 1-5"])
    rhythm  = st.radio("Rhythm", ["Whole note", "Two feel", "Beats 2 & 4", "Charleston"])
    bpm     = st.slider("BPM", 40, 200, 110)

# Color legend
legend = {
    ('Guide Tones', 'Highlight 3+7'): "🔵 3rd & 7th",
    ('Guide Tones', 'Each interval'): "🔵 3rd   🟢 7th",
    ('Rootless',    'Highlight 3+7'): "🔵 3rd & 7th   🔴 9th",
    ('Rootless',    'Each interval'): "🔵 3rd   🟢 7th   🔴 9th",
    ('Full Chord',  'Highlight 3+7'): "⚫ Root   🔵 3rd & 7th   🔴 9th   🟣 extensions",
    ('Full Chord',  'Each interval'): "⚫ Root   🔵 3rd   🟢 7th   🔴 9th   🟣 extensions",
}
st.caption(legend.get((note_mode, color_mode), ""))
st.caption("Shorthands: M or ^ = maj7 · - = m7 · h = half-dim  e.g. EbM  Bb-  Bh")

# ── Progression Builder ───────────────────────────────────────────────────────
with st.expander("🎼 Progression Builder", expanded=False):
    st.caption("Select progressions, set repeat counts, choose a key, then click Build.")

    key_sel = st.selectbox("Key", KEY_ORDER, index=0)

    # Table header
    h1, h2, h3 = st.columns([3, 4, 1])
    h1.markdown("**Progression**")
    h2.markdown("**Description**")
    h3.markdown("**Repeat**")

    selections = []
    for i, (name, desc, chords) in enumerate(PROGRESSIONS):
        c1, c2, c3 = st.columns([3, 4, 1])
        checked = c1.checkbox(name, key=f'prog_{i}', value=False)
        c2.caption(desc)
        repeats = c3.number_input("", min_value=1, max_value=8, value=1,
                                  key=f'rep_{i}', label_visibility='collapsed')
        if checked:
            selections.append((chords, int(repeats)))

    if st.button("Build Progression →", type="primary"):
        if selections:
            all_chords = []
            for chords, repeats in selections:
                transposed = transpose_progression(chords, key_sel)
                for _ in range(repeats):
                    all_chords.extend(transposed)
            st.session_state['built_progression'] = ' '.join(all_chords)
            st.success(f"Built {len(all_chords)} chords — see progression box below.")
        else:
            st.warning("Select at least one progression.")

# ── Score name and chord input ────────────────────────────────────────────────
score_name = st.text_input("Score name:", "my_changes")

# Use built progression if available, otherwise keep previous value
default_prog = st.session_state.get('built_progression',
                                    "Dm7 G7 Cmaj7 Cmaj7\nAm7 D7 Gmaj7 Gmaj7")
user_prog = st.text_area("Chord progression:", value=default_prog, height=120)

if st.button("Generate Score"):
    chord_list = user_prog.split()
    safe_name  = re.sub(r'[^a-zA-Z0-9_\-]', '_', score_name.strip()) or "my_changes"
    if chord_list:
        with st.spinner("Building score…"):
            xml_obj, mid_obj, skipped = generate_files(
                chord_list, bpm, hand, b_style,
                note_mode, voicing_mode, n_notes, color_mode,
                score_title=score_name.strip() or "Jazz Guide Tones",
                rhythm=rhythm
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
safe = st.session_state.safe_name
if st.session_state.mid:
    c1.download_button("🎵 MIDI",  st.session_state.mid, f"{safe}.mid")
if st.session_state.xml:
    c2.download_button("💾 Score", st.session_state.xml, f"{safe}.musicxml")

