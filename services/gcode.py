"""Read the printing time and filament weight a slicer already wrote into its own G-code.

Every mainstream slicer comments its estimate near the top or bottom of the file: Bambu Studio and
OrcaSlicer (this shop's printers) write "total filament weight [g]" and "total estimated time";
PrusaSlicer/SuperSlicer write "filament used [g]" and "estimated printing time"; Cura writes
";TIME:" in seconds and ";Filament weight = " in grams when that plugin is on. Reading these saves
retyping numbers the slicer already computed, and keeps the two in one place instead of guessed twice.
"""
import re

_TIME_PATTERNS = (
    r';\s*total estimated time\s*[:=]\s*([\ddhms\s]+)',
    r';\s*model printing time\s*[:=]\s*([\ddhms\s]+)',
    r';\s*estimated printing time \(normal mode\)\s*=\s*([\ddhms\s]+)',
    r';\s*estimated printing time\s*=\s*([\ddhms\s]+)',
)
_SECONDS_PATTERN = r';TIME:\s*(\d+)'
_GRAMS_PATTERNS = (
    r';\s*total filament weight \[g\]\s*[:=]\s*([\d.,\s]+)',
    r';\s*filament used \[g\]\s*=\s*([\d.,\s]+)',
    r';\s*filament_used_g\s*=\s*([\d.,\s]+)',
)
_CURA_GRAMS = r';\s*Filament weight\s*=\s*([\d.]+)\s*g'


def _duration_to_minutes(text):
    """'2h 35m 12s' / '1d 2h' / '45m' -> whole minutes, rounded up so a part-minute still counts."""
    units = {'d': 1440, 'h': 60, 'm': 1, 's': 1 / 60}
    total = 0.0
    found = False
    for amount, unit in re.findall(r'(\d+)\s*([dhms])', text):
        total += int(amount) * units[unit]
        found = True
    return int(-(-total // 1)) if found else None  # ceil without importing math


def parse(text):
    """dict(minutes, grams, source) from a slicer's own header/footer comments; any field can be None."""
    minutes = None
    for pattern in _TIME_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            minutes = _duration_to_minutes(match.group(1))
            if minutes:
                break
    if minutes is None:
        match = re.search(_SECONDS_PATTERN, text)
        if match:
            minutes = int(-(-int(match.group(1)) // 60))
    grams = None
    for pattern in _GRAMS_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            # Multi-color prints list one value per extruder, comma-separated; the print's total is their sum.
            values = [float(v) for v in re.findall(r'[\d.]+', match.group(1))]
            if values:
                grams = round(sum(values), 2)
                break
    if grams is None:
        match = re.search(_CURA_GRAMS, text, re.IGNORECASE)
        if match:
            grams = round(float(match.group(1)), 2)
    return dict(minutes=minutes, grams=grams, found=bool(minutes or grams))


def parse_file(upload):
    """parse() from an uploaded file-like object (e.g. st.file_uploader); only reads its text, never runs it."""
    raw = upload.getvalue()
    text = raw.decode('utf-8', errors='ignore') if isinstance(raw, bytes) else raw
    return parse(text)
