"""A development project's journal: notes, technical reports of each test, and links to its files.

Notes and reports are the project's own working record, so they can be edited and deleted (with a
revision check against another window), unlike financial records. A report states the result of the
test and may name the print it tested by job code. Links point at a web page or at a file or folder
on this computer or the network; services.local_files opens the latter.
"""
import re
from urllib.parse import unquote

from db import connect
from utils.dates import timestamp

KINDS = ('Nota', 'Reporte')
RESULTS = ('Aprobado', 'Ajustar', 'Rechazado')
TARGET_HINT = 'Usa un enlace https:// o la ruta completa de un archivo o carpeta, por ejemplo C:\\Proyectos\\pieza.3mf.'


def _text(value, message, limit, *, required=True):
    text = str(value or '').strip()
    if required and not text:
        raise ValueError(message)
    if len(text) > limit:
        raise ValueError(f'Máximo {limit} caracteres.')
    return text


def normalize_target(target):
    """A pasted address, cleaned: quotes from "Copiar como ruta de acceso" removed, file:// turned into a path."""
    text = str(target or '').strip().strip('"\'').strip()
    if not text:
        raise ValueError('Pega la dirección del archivo, carpeta o enlace.')
    if len(text) > 2000:
        raise ValueError('La dirección es demasiado larga.')
    if re.match(r'^www\.\S+$', text, re.I):
        text = 'https://' + text
    if re.match(r'^https?://\S+$', text, re.I):
        return text
    if re.match(r'^file:/+', text, re.I):
        path = unquote(re.sub(r'^file:/+', '', text, flags=re.I))
        text = path.replace('/', '\\') if re.match(r'^[a-zA-Z]:', path) else '/' + path
    if re.match(r'^[a-zA-Z]:[\\/]', text) or text.startswith('\\\\') or text.startswith('/'):
        return text
    raise ValueError(TARGET_HINT)


def is_web(target):
    return bool(re.match(r'^https?://', target, re.I))


def default_label(target):
    """What to call a link nobody named: the file or folder name, or the site."""
    if is_web(target):
        return re.sub(r'^https?://(www\.)?', '', target, flags=re.I).split('/')[0] or target
    return re.split(r'[\\/]', target.rstrip('\\/'))[-1] or target


def parse_links(text):
    """One link per line, "Etiqueta | dirección" or just the address."""
    links = []
    for line in str(text or '').splitlines():
        if not line.strip():
            continue
        label, _, target = line.rpartition('|') if '|' in line else ('', '', line)
        target = normalize_target(target)
        links.append((label.strip() or default_label(target), target))
    return links


def _project(conn, order_id):
    if not conn.execute('SELECT 1 FROM development_projects WHERE order_id=?', (order_id,)).fetchone():
        raise ValueError('El proyecto de desarrollo ya no existe.')


def _job_of_project(conn, order_id, job_code):
    return conn.execute('''SELECT 1 FROM production_jobs j JOIN parts p ON p.id=j.part_id JOIN items i ON i.id=p.item_id
        WHERE j.code=? AND i.order_id=?''', (job_code, order_id)).fetchone()


def _insert_links(conn, order_id, entry_id, links, request_key, stamp):
    for index, (label, target) in enumerate(links):
        conn.execute('''INSERT INTO development_links(order_id,entry_id,label,target,pinned,created_at,request_key)
            VALUES(?,?,?,?,0,?,?)''', (order_id, entry_id, _text(label, 'Escribe el nombre del enlace.', 160), target, stamp, f'{request_key}:link:{index}'))


def save_entry(order_id, kind, title, body='', *, result=None, job_code='', links=(), entry_id=None, expected_revision=None, request_key):
    """A new note or report (entry_id None) or an edit of one; `links` are added to it in the same save."""
    if kind not in KINDS:
        raise ValueError('Elige nota o reporte técnico.')
    title = _text(title, 'Escribe el título.', 160)
    body = _text(body, '', 20000, required=False)
    if kind == 'Nota':
        result, job_code = None, ''
    elif result not in (None, *RESULTS):
        raise ValueError('Elige un resultado válido.')
    job_code = str(job_code or '').strip()
    links = [(label, normalize_target(target)) for label, target in links]
    if not request_key:
        raise ValueError('Vuelve a abrir el formulario.')
    stamp = timestamp()
    with connect(write=True) as conn:
        _project(conn, order_id)
        if job_code and not _job_of_project(conn, order_id, job_code):
            raise ValueError('Esa impresión no pertenece a este proyecto.')
        if entry_id is None:
            if prior := conn.execute('SELECT id FROM development_entries WHERE request_key=?', (request_key,)).fetchone():
                return prior['id']
            entry_id = conn.execute('''INSERT INTO development_entries(order_id,kind,title,body,result,job_code,created_at,updated_at,request_key)
                VALUES(?,?,?,?,?,?,?,?,?)''', (order_id, kind, title, body, result, job_code, stamp, stamp, request_key)).lastrowid
        else:
            updated = conn.execute('''UPDATE development_entries SET kind=?,title=?,body=?,result=?,job_code=?,revision=revision+1,updated_at=?
                WHERE id=? AND order_id=? AND revision=?''', (kind, title, body, result, job_code, stamp, entry_id, order_id, expected_revision)).rowcount
            if not updated:
                row = conn.execute('SELECT * FROM development_entries WHERE id=?', (entry_id,)).fetchone()
                # A double click: the first save already wrote exactly this.
                if row and row['revision'] == (expected_revision or 0) + 1 and (row['kind'], row['title'], row['body'], row['result'], row['job_code']) == (kind, title, body, result, job_code):
                    return entry_id
                raise ValueError('La entrada cambió en otra ventana. Actualiza antes de guardar.')
        _insert_links(conn, order_id, entry_id, links, request_key, stamp)
        return entry_id


def delete_entry(entry_id, *, expected_revision):
    """Removes the note or report and the links attached to it."""
    with connect(write=True) as conn:
        if not conn.execute('DELETE FROM development_entries WHERE id=? AND revision=?', (entry_id, expected_revision)).rowcount:
            raise ValueError('La entrada cambió o ya no existe. Actualiza la vista.')


def add_link(order_id, target, label='', *, entry_id=None, pinned=False, request_key):
    target = normalize_target(target)
    label = str(label or '').strip() or default_label(target)
    if not request_key:
        raise ValueError('Vuelve a abrir el formulario.')
    with connect(write=True) as conn:
        _project(conn, order_id)
        if prior := conn.execute('SELECT id FROM development_links WHERE request_key=?', (request_key,)).fetchone():
            return prior['id']
        if entry_id is not None and not conn.execute('SELECT 1 FROM development_entries WHERE id=? AND order_id=?', (entry_id, order_id)).fetchone():
            raise ValueError('La nota o reporte ya no existe.')
        return conn.execute('''INSERT INTO development_links(order_id,entry_id,label,target,pinned,created_at,request_key)
            VALUES(?,?,?,?,?,?,?)''', (order_id, entry_id, _text(label, 'Escribe el nombre del enlace.', 160), target, int(bool(pinned)), timestamp(), request_key)).lastrowid


def delete_link(link_id):
    with connect(write=True) as conn:
        if not conn.execute('DELETE FROM development_links WHERE id=?', (link_id,)).rowcount:
            raise ValueError('El enlace ya no existe.')


def set_pinned(item, item_id, pinned):
    """Pinned notes and reports lead the journal; pinned links become the project's quick access."""
    table = {'entry': 'development_entries', 'link': 'development_links'}[item]
    with connect(write=True) as conn:
        if not conn.execute(f'UPDATE {table} SET pinned=? WHERE id=?', (int(bool(pinned)), item_id)).rowcount:
            raise ValueError('Ya no existe. Actualiza la vista.')


def journal(order_id):
    """The project's entries (pinned first, newest first) with their links, and every link of the project."""
    with connect() as conn:
        entries = [dict(r) for r in conn.execute('SELECT * FROM development_entries WHERE order_id=? ORDER BY pinned DESC, created_at DESC, id DESC', (order_id,))]
        links = [dict(r) for r in conn.execute('SELECT * FROM development_links WHERE order_id=? ORDER BY pinned DESC, id DESC', (order_id,))]
    titles = {e['id']: e['title'] for e in entries}
    for link in links:
        link['entry_title'] = titles.get(link['entry_id'], '')
        link['web'] = is_web(link['target'])
    for entry in entries:
        entry['links'] = [l for l in links if l['entry_id'] == entry['id']]
    reports = [e for e in entries if e['kind'] == 'Reporte']
    return dict(entries=entries, links=links, reports=reports,
                results={r: sum(e['result'] == r for e in reports) for r in (*RESULTS, None)})


def overview():
    """Per project: how many notes, reports and links, the latest report's result and the pinned links."""
    with connect() as conn:
        entries = [dict(r) for r in conn.execute('SELECT order_id,kind,result,created_at FROM development_entries ORDER BY created_at, id')]
        links = [dict(r) for r in conn.execute('SELECT * FROM development_links ORDER BY id')]
    result = {}
    for e in entries:
        own = result.setdefault(e['order_id'], dict(notes=0, reports=0, links=0, last_result=None, last_report=None, quick=[]))
        own['notes' if e['kind'] == 'Nota' else 'reports'] += 1
        if e['kind'] == 'Reporte':
            own['last_result'], own['last_report'] = e['result'], e['created_at']
    for link in links:
        own = result.setdefault(link['order_id'], dict(notes=0, reports=0, links=0, last_result=None, last_report=None, quick=[]))
        own['links'] += 1
        if link['pinned']:
            own['quick'].append(dict(link, web=is_web(link['target'])))
    return result
