"""NIMUS OS look: one stylesheet over the native theme in .streamlit/config.toml.

The theme file sets colors, radius and fonts; this layer only adds what it cannot express: tighter
page margins, one button system, metric and card surfaces, menus, dialogs and the sidebar.
Selectors use Streamlit's stable test ids and the st-key-<key> class of keyed containers.

Each environment has its own accent, set as CSS variables after the sidebar knows where you are:
Taller is teal, Negocio is navy, and the Colección Origen page is black with gold. The sidebar follows
the area picked in its switch, so changing between Taller and Negocio changes the whole frame.
"""
import streamlit as st
from views.kind_style import STYLE as KIND_STYLE

INK = '#18262E'
MUTED = '#5E6E77'
SURFACE = '#F7FAFB'
SHADOW = '0 1px 2px rgba(16,40,48,.06), 0 6px 16px -10px rgba(16,40,48,.18)'

# accent: text, borders and active controls · top/deep: the primary button's fill · on: text on that fill
# soft/tint: hover and selected surfaces · glow: shadow and focus ring.
PALETTES = {
    'Taller': dict(accent='#0F6F78', top='#14828C', deep='#0B5A62', on='#FFFFFF', soft='#F2F9F9', tint='#E3F1F1', glow='15,111,120'),
    'Negocio': dict(accent='#2F4C9A', top='#3A5BB0', deep='#223B7A', on='#FFFFFF', soft='#F2F5FC', tint='#E3E9F8', glow='47,76,154'),
    # Colección Origen: black buttons with gold letters, gold for what is selected.
    'Origen': dict(accent='#9A7522', top='#2B2720', deep='#14120E', on='#E8CC85', soft='#FBF6E9', tint='#F4E8C8', glow='154,117,34'),
}
SIDEBARS = {
    'Taller': dict(back='#0F252C', raised='#1B3840', active='#8FD3D3', label='#9FB8BD'),
    'Negocio': dict(back='#141A33', raised='#222B50', active='#B4C3F3', label='#A3AED0'),
}

# Every button kind, including those inside forms, so a form's button looks like any other.
PRIMARY = '[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"]'
SECONDARY = '[data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"]'
TERTIARY = '[data-testid="stBaseButton-tertiary"], [data-testid="stBaseButton-tertiaryFormSubmit"]'


def _scoped(selectors, scopes=('[data-testid="stMain"]', 'div[role="dialog"]'), state=''):
    return ', '.join(f'{scope} {s.strip()}{state}' for scope in scopes for s in selectors.split(','))


CSS = f"""<style>
:root {{ --nx-accent:#0F6F78; --nx-top:#14828C; --nx-deep:#0B5A62; --nx-on:#fff; --nx-soft:#F2F9F9; --nx-tint:#E3F1F1; --nx-glow:15,111,120; }}
/* Page frame: less empty space above the title, a readable maximum width. */
[data-testid="stMainBlockContainer"] {{ padding: 1.6rem 2.4rem 4rem; max-width: 1560px; }}
[data-testid="stHeader"] {{ background: transparent; }}
h1, h2, h3 {{ letter-spacing: -.015em; }}
[data-testid="stCaptionContainer"] {{ color: {MUTED}; }}

/* Buttons: one height, clear weight, visible feedback, the same in pages, dialogs and forms. */
[data-testid^="stBaseButton-"] {{ font-weight: 600; min-height: 2.35rem; border-radius: 10px; -webkit-tap-highlight-color: transparent;
    transition-property: background-color, border-color, color, box-shadow, filter; transition-duration: .15s; transition-timing-function: ease-out; }}
/* Pressing gives way a little, the same on every button; movement only when the system allows it. */
@media (prefers-reduced-motion: no-preference) {{
    [data-testid^="stBaseButton-"] {{ transition-property: background-color, border-color, color, box-shadow, filter, scale; }}
    [data-testid^="stBaseButton-"]:active:not(:disabled) {{ scale: .96; }}
}}
[data-testid^="stBaseButton-"]:focus-visible {{ outline: none; box-shadow: 0 0 0 3px rgba(var(--nx-glow),.35) !important; }}
[data-testid^="stBaseButton-"]:disabled {{ opacity: .5; cursor: not-allowed; box-shadow: none !important; filter: none !important; }}
[data-testid^="stBaseButton-"] [data-testid="stIconMaterial"] {{ font-size: 1.15em; }}
/* Primary: the one important action of a zone, a deeper fill with a light top edge and a lifted shadow. */
{PRIMARY} {{ background: linear-gradient(180deg, var(--nx-top) 0%, var(--nx-deep) 100%); border: 1px solid var(--nx-deep); color: var(--nx-on);
    font-weight: 650; letter-spacing: .005em;
    box-shadow: inset 0 1px 0 rgba(255,255,255,.2), 0 1px 2px rgba(var(--nx-glow),.35), 0 8px 16px -8px rgba(var(--nx-glow),.6); }}
{PRIMARY.replace('"]', '"]:disabled')} {{ background: #C9D3D7; border-color: #C9D3D7; color: #fff; }}
/* Secondary: a white key with a soft lift; hover takes the environment's accent. */
{_scoped(SECONDARY)} {{ background: #fff; border-color: #D3DDE2; color: {INK}; box-shadow: 0 1px 2px rgba(16,40,48,.06); }}
/* Tertiary: text actions in the accent, a tint on hover. */
{_scoped(TERTIARY)} {{ color: var(--nx-accent); }}
/* Menus (popovers) read as secondary keys. */
[data-testid="stMain"] [data-testid="stPopoverButton"], div[role="dialog"] [data-testid="stPopoverButton"] {{ font-weight: 600; border-radius: 10px; }}

/* Segmented controls, pills and tabs: what is picked takes the environment's accent. */
[data-testid="stButtonGroup"] button {{ font-weight: 600; }}
[data-testid="stMain"] [data-testid="stButtonGroup"] button[data-selected="true"], div[role="dialog"] [data-testid="stButtonGroup"] button[data-selected="true"] {{
    background: var(--nx-tint) !important; border-color: var(--nx-accent) !important; color: var(--nx-accent) !important; }}

/* Hover only where a pointer can hover: on the workshop's tablets a tapped key would stay lit as if picked. */
@media (hover: hover) {{
{PRIMARY.replace('"]', '"]:hover:not(:disabled)')} {{ filter: brightness(1.08); color: var(--nx-on); border-color: var(--nx-deep);
    box-shadow: inset 0 1px 0 rgba(255,255,255,.26), 0 2px 4px rgba(var(--nx-glow),.35), 0 10px 18px -8px rgba(var(--nx-glow),.7); }}
{_scoped(SECONDARY, state=':hover:not(:disabled)')} {{ border-color: var(--nx-accent); color: var(--nx-accent); background: var(--nx-soft);
    box-shadow: 0 1px 2px rgba(16,40,48,.06), 0 6px 12px -8px rgba(var(--nx-glow),.45); }}
{_scoped(TERTIARY, state=':hover:not(:disabled)')} {{ background: var(--nx-soft); color: var(--nx-accent); }}
[data-testid="stMain"] [data-testid="stPopoverButton"]:hover {{ border-color: var(--nx-accent); color: var(--nx-accent); background: var(--nx-soft); }}
[data-testid="stMain"] [data-testid="stButtonGroup"] button:not([data-selected="true"]):hover, div[role="dialog"] [data-testid="stButtonGroup"] button:not([data-selected="true"]):hover {{
    border-color: var(--nx-accent) !important; color: var(--nx-accent) !important; }}
[data-testid="stNumberInputStepDown"]:hover, [data-testid="stNumberInputStepUp"]:hover {{ color: var(--nx-accent); opacity: 1; }}
[data-testid="stMain"] [data-testid="stExpander"] summary:hover {{ background: #F4F8F9; }}
[class*="st-key-kind-"]:hover {{ box-shadow: 0 1px 2px rgba(16,40,48,.06), 0 10px 22px -12px rgba(16,40,48,.28); }}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover {{ background: rgba(255,255,255,.07); }}
}}
[data-testid="stMain"] [data-testid="stTab"][aria-selected="true"] p, div[role="dialog"] [data-testid="stTab"][aria-selected="true"] p {{ color: var(--nx-accent); }}
[data-testid="stMain"] [data-testid="stTab"] .react-aria-SelectionIndicator, div[role="dialog"] [data-testid="stTab"] .react-aria-SelectionIndicator {{ background-color: var(--nx-accent) !important; }}
[data-testid="stMain"] [data-testid="stMarkdownContainer"] a, [data-testid="stMain"] [data-testid="stPageLink-NavLink"] p {{ color: var(--nx-accent); }}

/* Section headings: their icon takes the environment's accent, so a page's parts read at a glance. */
[data-testid="stMain"] [data-testid="stHeading"] [data-testid="stIconMaterial"], div[role="dialog"] [data-testid="stHeading"] [data-testid="stIconMaterial"] {{ color: var(--nx-accent); }}
[data-testid="stMain"] [data-testid="stExpander"] summary [data-testid="stIconMaterial"] {{ color: var(--nx-accent); }}
/* Under the page title, one quiet line on what the page is for. */
[data-testid="stMainBlockContainer"] > div > div > div > [data-testid="stCaptionContainer"]:first-of-type {{ font-size: .86rem; }}
/* Badges: a little more weight so a state reads before the text around it. */
[data-testid="stMain"] .stMarkdownBadge, [data-testid="stMain"] [data-testid="stBadge"] {{ font-weight: 600; }}
/* Segmented controls and pills: the same comfortable height everywhere. */
[data-testid="stMain"] [data-testid="stButtonGroup"] button {{ min-height: 2.25rem; }}

/* Quantities: steppers stay but get out of the way of the number. */
[data-testid="stNumberInputStepDown"], [data-testid="stNumberInputStepUp"] {{ color: {MUTED}; opacity: .8; }}
[data-testid="stNumberInputField"], [data-testid="stTextInputField"] {{ font-variant-numeric: tabular-nums; }}

/* Metrics as compact cards. */
[data-testid="stMetric"] {{ background: linear-gradient(180deg, #fff, {SURFACE}); }}
[data-testid="stMetricLabel"] p {{ font-size: .74rem; text-transform: uppercase; letter-spacing: .05em; font-weight: 650; color: {MUTED}; }}
[data-testid="stMetricValue"] {{ font-weight: 700; letter-spacing: -.02em; }}

/* Expanders, alerts, menus and dialogs share the same soft surface. */
[data-testid="stExpander"] details {{ border-radius: 14px; overflow: hidden; }}
[data-testid="stExpander"] summary {{ font-weight: 600; }}
[data-testid="stAlert"] {{ border-radius: 12px; }}
[data-testid="stPopoverBody"] {{ border-radius: 14px; box-shadow: 0 12px 32px -12px rgba(16,40,48,.35); overscroll-behavior: contain; }}
/* Scrolling past the end of a dialog or the sidebar never drags the page behind it. */
div[role="dialog"] {{ border-radius: 18px; overscroll-behavior: contain; }}
[data-testid="stSidebarContent"] {{ overscroll-behavior: contain; }}
[data-testid="stTab"] p {{ font-weight: 600; }}
[data-testid="stDataFrame"] {{ border-radius: 12px; overflow: hidden; }}
[data-testid="stProgress"] > div > div > div {{ border-radius: 99px; }}

/* Keyed cards of the workshop: white surface with a soft lift. */
[class*="st-key-kind-"], [class*="st-key-floor-"], [class*="st-key-pick-"], [class*="st-key-panel-"] {{ background-color: #fff; box-shadow: {SHADOW}; }}
/* A form section: a quiet tinted block that groups related fields. */
[class*="st-key-section-"] {{ background: {SURFACE}; border-radius: 14px; padding: .85rem 1rem; }}
[class*="st-key-section-"] [data-testid="stMarkdownContainer"] strong:first-child {{ color: {INK}; }}

/* Hoy: the briefing line, the pulse cards (edge by their worst alert) and the agenda. */
.today-brief {{ display: flex; flex-direction: column; gap: .1rem; padding: .2rem 0 .1rem; }}
.today-hello {{ font-size: 1.3rem; font-weight: 700; letter-spacing: -.015em; color: {INK}; }}
.today-line {{ font-size: .92rem; color: {MUTED}; }}
[class*="st-key-pulse-"] {{ background: #fff; box-shadow: {SHADOW}; border-left: 4px solid var(--nx-accent) !important; flex: 1 1 0; min-width: 160px; }}
[class*="st-key-pulse-red-"] {{ border-left-color: #B2434C !important; }}
[class*="st-key-pulse-orange-"] {{ border-left-color: #B0691F !important; }}
[class*="st-key-pulse-"] [data-testid="stCaptionContainer"] {{ text-transform: uppercase; letter-spacing: .05em; font-size: .72rem; font-weight: 650; }}
[class*="st-key-pulse-"] {TERTIARY.split(',')[0]} {{ justify-content: flex-start; padding-left: 0; min-height: 1.9rem; }}
[class*="st-key-pulse-"] {TERTIARY.split(',')[0]} > div {{ justify-content: flex-start; }}
.pulse-value {{ font-size: 1.7rem; font-weight: 700; letter-spacing: -.02em; line-height: 1.15; font-variant-numeric: tabular-nums; color: {INK}; }}
[class*="st-key-money-row-"] {{ border-bottom: 1px solid #EEF2F4; padding-bottom: .3rem; }}
[class*="st-key-money-row-"] [data-testid="stMarkdownContainer"] p {{ font-variant-numeric: tabular-nums; }}

/* Negocio: headline numbers as metric cards with a colored left edge by urgency, same language as Hoy's pulse. */
[class*="st-key-mcard-"] [data-testid="stMetric"] {{ border-left: 4px solid var(--nx-accent) !important; }}
[class*="st-key-mcard-orange-"] [data-testid="stMetric"] {{ border-left-color: #B0691F !important; }}
[class*="st-key-mcard-red-"] [data-testid="stMetric"] {{ border-left-color: #B2434C !important; }}

/* Sidebar navigation: rounded rows and a clear current page. */
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] {{ border-radius: 10px; padding: .32rem .65rem; transition: background .12s ease; }}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{ text-transform: uppercase; letter-spacing: .06em; font-size: .7rem; font-weight: 650; margin-top: .35rem; }}
/* A page's live count sits at the right edge of its row; the button counts read the same way. */
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] > span:last-child, [data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] [data-testid="stMarkdownContainer"] {{ flex: 1; width: 100%; }}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] p {{ display: flex; align-items: center; gap: .25rem; width: 100%; }}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] p .stMarkdownBadge:first-of-type {{ margin-left: auto; }}
[data-testid="stSidebar"] .stMarkdownBadge {{ font-size: .7rem !important; font-weight: 700; padding: 0 .4rem; line-height: 1.35; font-variant-numeric: tabular-nums; }}
[data-testid="stSidebar"] .st-key-notifications_open button {{ justify-content: flex-start; }}
</style>"""


# Button color by intent, never by importance: hierarchy stays primary (filled) > secondary > tertiary.
# A secondary or tertiary button takes a soft tone (tinted surface, colored text); a primary one, the solid
# color of its intent, kept for confirmations. Buttons opt in by their key: the container of a keyed
# widget gets the class st-key-<key>, followed by a space, so "<fragment> " matches the end of a key.
TONES = {
    # name: (solid, text, soft background)
    'success': ('#2F7A57', '#235E43', '#E3F2EA'),
    'warning': ('#B0691F', '#86501A', '#FBEEDC'),
    'danger': ('#B2434C', '#922F39', '#FBE9EA'),
    'stock': ('#3D6FA3', '#2D5580', '#E5EEF8'),
    # Starting or resuming a print: the blue of "printing", the state the print is about to take.
    'start': ('#2F67B2', '#244F8A', '#E3EDFA'),
}
INTENTS = {
    # Completing work or handing it over.
    'success': ('_finish ', 'machine_finish_', 'deliver_', 'prepare_deliver '),
    # Stopping, reporting a problem or fixing a schedule.
    'warning': ('_pause ', 'machine_pause_', '_failure ', 'control_failure ', '_reprint ', 'quality_reprint_', '_detach ', 'queue_fix_', 'avail_return_'),
    # Removing, blocking, voiding or cancelling: always read twice.
    'danger': ('_delete', 'delete_execute ', '_block ', 'machine_remove_confirm ', '_void ', '_void_', '_cancel '),
    # Taking pieces already in inventory instead of printing them.
    'stock': ('order_cover_', '_take ', '_ride_', 'st-key-cover_', 'avail_take_'),
    'start': ('_start ', 'machine_start_', 'today_start_'),
}


def _tone_css(name, fragments):
    solid, text, soft = TONES[name]

    def select(kind, state=''):
        return ', '.join(f'[class*="st-key-"][class*="{f}"] button[data-testid="stBaseButton-{k}"]{state}'
                         for f in fragments for k in (kind, kind + 'FormSubmit'))
    return (f'{select("secondary")} {{ background: {soft} !important; color: {text} !important; border-color: {solid}55 !important; }}'
            f'{select("tertiary")} {{ color: {text} !important; }}'
            f'{select("primary")} {{ background: {solid} !important; border-color: {solid} !important; color: #fff !important; '
            f'box-shadow: 0 1px 2px {solid}40, 0 6px 14px -8px {solid}99 !important; }}'
            '@media (hover: hover) {'
            f'{select("secondary", ":hover")} {{ background: {solid}22 !important; border-color: {solid} !important; color: {text} !important; }}'
            f'{select("tertiary", ":hover")} {{ background: {soft} !important; }}'
            f'{select("primary", ":hover")} {{ filter: brightness(1.07); }}'
            '}')


TONE_CSS = '<style>' + ''.join(_tone_css(name, fragments) for name, fragments in INTENTS.items()) + '</style>'


def inject():
    st.html(CSS + KIND_STYLE + TONE_CSS)


def environment(page_area, sidebar_area, *, origin=False):
    """Accent of the page (its area, or Colección Origen) and of the sidebar (the area picked in its switch)."""
    p = PALETTES['Origen' if origin else page_area if page_area in PALETTES else 'Taller']
    s = SIDEBARS.get(sidebar_area, SIDEBARS['Taller'])
    css = (f":root {{ --nx-accent:{p['accent']}; --nx-top:{p['top']}; --nx-deep:{p['deep']}; --nx-on:{p['on']}; --nx-soft:{p['soft']}; "
           f"--nx-tint:{p['tint']}; --nx-glow:{p['glow']}; }}"
           f"[data-testid='stSidebar'], [data-testid='stSidebar'] > div:first-child {{ background-color:{s['back']} !important; transition: background-color .25s ease; }}"
           f"[data-testid='stSidebar'] [data-testid='stCaptionContainer'] {{ color:{s['label']}; }}"
           f"[data-testid='stSidebar'] [data-testid='stButtonGroup'] button[data-selected='true'] {{ background:{s['raised']} !important; color:{s['active']} !important; border-color:{s['active']} !important; }}"
           # The page you are on: the raised surface and an accent edge of the area picked in the switch.
           f"[data-testid='stSidebar'] .st-key-nav-current [data-testid='stPageLink-NavLink'] {{ background:{s['raised']}; box-shadow: inset 3px 0 0 {s['active']}; }}"
           f"[data-testid='stSidebar'] .st-key-nav-current [data-testid='stPageLink-NavLink'] p {{ color:#fff; font-weight:650; }}"
           f"[data-testid='stSidebar'] .st-key-nav-current [data-testid='stIconMaterial'] {{ color:{s['active']} !important; }}")
    if origin:
        # The Colección Origen page: a fine gold rule under the title, the same black-and-gold as its chips in the queue.
        css += ("[data-testid='stMainBlockContainer'] [data-testid='stHeading'] h2 { border-bottom: 2px solid #B8902F; padding-bottom: .15rem; display: inline-block; }"
                "[data-testid='stMain'] [data-testid='stMetric'] { border-color: #E6D3A3 !important; background: linear-gradient(180deg,#fff,#FCF8EE); }")
    st.html(f'<style>{css}</style>')
