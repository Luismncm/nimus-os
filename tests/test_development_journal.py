import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import db
from services import development as d, development_journal as dj, local_files
from services.queries import load_snapshot
from tests import test_development as fixture
from tests.backends import sqlite_only

APP = str(Path(__file__).resolve().parents[1] / 'app.py')


class JournalTest(unittest.TestCase):
    setUp = fixture.DevelopmentTest.setUp
    launch = fixture.DevelopmentTest.launch

    def job_code(self):
        jid = self.launch()
        return next(j['code'] for j in load_snapshot()['jobs'] if j['id'] == jid)

    def test_report_names_its_print_and_result_and_carries_links(self):
        code = self.job_code()
        eid = dj.save_entry(self.project, 'Reporte', 'Ajuste 0.2 mm', 'La bisagra entra justa.', result='Ajustar', job_code=code,
                            links=dj.parse_links('Modelo v3 | "C:\\Proyectos\\Nimbus\\pantalla v3.3mf"\nwww.example.com/fotos'), request_key='r1')
        self.assertEqual(dj.save_entry(self.project, 'Reporte', 'Ajuste 0.2 mm', request_key='r1'), eid)  # A double click saves once.
        data = dj.journal(self.project)
        report = data['entries'][0]
        self.assertEqual((report['result'], report['job_code']), ('Ajustar', code))
        self.assertEqual([(l['label'], l['target']) for l in report['links']],
                         [('example.com', 'https://www.example.com/fotos'), ('Modelo v3', 'C:\\Proyectos\\Nimbus\\pantalla v3.3mf')])
        self.assertEqual(data['results']['Ajustar'], 1)
        with self.assertRaises(ValueError):  # A print of another order is not this project's test.
            dj.save_entry(self.project, 'Reporte', 'Otra', job_code='JOB-9999', request_key='r2')
        # A note never carries a result.
        nid = dj.save_entry(self.project, 'Nota', 'Idea', result='Aprobado', request_key='n1')
        self.assertIsNone(next(e for e in dj.journal(self.project)['entries'] if e['id'] == nid)['result'])

    def test_edit_checks_revision_and_delete_takes_its_links(self):
        eid = dj.save_entry(self.project, 'Nota', 'Pendiente', links=[('Carpeta', 'C:\\Proyectos')], request_key='n1')
        dj.save_entry(self.project, 'Nota', 'Pendiente resuelto', entry_id=eid, expected_revision=0, request_key='e1')
        self.assertEqual(dj.save_entry(self.project, 'Nota', 'Pendiente resuelto', entry_id=eid, expected_revision=0, request_key='e1'), eid)
        with self.assertRaises(ValueError):
            dj.save_entry(self.project, 'Nota', 'Desde otra ventana', entry_id=eid, expected_revision=0, request_key='e2')
        dj.add_link(self.project, 'https://drive.google.com/x', 'Drive', pinned=True, request_key='l1')
        self.assertEqual([l['label'] for l in dj.overview()[self.project]['quick']], ['Drive'])
        dj.delete_entry(eid, expected_revision=1)
        data = dj.journal(self.project)
        self.assertEqual((data['entries'], [l['label'] for l in data['links']]), ([], ['Drive']))

    def test_addresses_are_cleaned_or_refused(self):
        self.assertEqual(dj.normalize_target('file:///C:/Proyectos/pieza%20v2.stl'), 'C:\\Proyectos\\pieza v2.stl')
        self.assertEqual(dj.normalize_target('  "\\\\NAS\\nimus\\modelos"  '), '\\\\NAS\\nimus\\modelos')
        self.assertEqual(dj.default_label('C:\\Proyectos\\Nimbus\\'), 'Nimbus')
        for bad in ('', 'pieza.stl', 'Proyectos\\pieza.stl', 'ftp://x'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                dj.normalize_target(bad)

    def test_closed_project_keeps_its_journal_writable(self):
        d.close_project(self.project)
        dj.save_entry(self.project, 'Reporte', 'Cierre: aprobado para producción', result='Aprobado', request_key='c1')
        self.assertEqual(dj.overview()[self.project]['last_result'], 'Aprobado')

    @sqlite_only
    def test_migration_from_35_adds_the_journal_with_backup(self):
        with db.connect(write=True) as conn:
            conn.execute('DROP TABLE development_links');conn.execute('DROP TABLE development_entries');conn.execute('PRAGMA user_version=35')
        db.init_db();db.init_db()
        with db.connect() as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], db.SCHEMA_VERSION)
        dj.save_entry(self.project, 'Nota', 'Después de migrar', request_key='m1')
        self.assertTrue(list(db.database_path().parent.joinpath('backups').glob('*pre-bitacora-desarrollo-v36*')))


class LocalFilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name) / 'pantalla.3mf';self.file.write_text('x')

    def test_status_and_what_opens(self):
        self.assertEqual([local_files.status(str(p)) for p in (self.tmp.name, self.file, Path(self.tmp.name) / 'no.stl')],
                         ['Carpeta', 'Archivo', 'No encontrado'])
        tool = Path(self.tmp.name) / 'instalar.exe';tool.write_text('x')
        with patch.object(local_files, '_launch') as launch:
            local_files.open_target(str(self.file))
            launch.assert_called_once_with(str(self.file))
            for refused in (str(tool), str(Path(self.tmp.name) / 'no.stl')):
                with self.subTest(refused=refused), self.assertRaises(ValueError):
                    local_files.open_target(refused)
            self.assertEqual(launch.call_count, 1)


class JournalUITest(unittest.TestCase):
    setUp = fixture.DevelopmentTest.setUp

    def clean(self, app):
        self.assertFalse(app.exception, [e.message for e in app.exception])

    def test_panel_writes_a_report_and_opens_a_pinned_file(self):
        tmp = tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        model = Path(tmp.name) / 'pantalla_v3.3mf';model.write_text('x')
        app = AppTest.from_file(APP, default_timeout=30).run().switch_page('views/development.py').run();self.clean(app)
        app.button(key=f'dev_panel_{self.project}').click().run();self.clean(app)
        self.assertTrue(any('Prototipo Nimbus' in m.value for m in app.markdown))
        app.button(key=f'dev_panel_report_{self.project}').click().run();self.clean(app)
        prefix = 'dev_entry_' + app.session_state['dialog_request_key']
        app.text_input(key=prefix + '_title').set_value('Prueba de ajuste')
        app.radio(key=prefix + '_result').set_value('Aprobado')
        app.text_area(key=prefix + '_body').set_value('Entra sin lijar.')
        app.text_area(key=prefix + '_links').set_value(f'Modelo | "{model}"')
        next(b for b in app.button if b.label == 'Guardar reporte técnico').click().run();self.clean(app)
        report = dj.journal(self.project)['reports'][0]
        self.assertEqual((report['title'], report['result'], [l['label'] for l in report['links']]), ('Prueba de ajuste', 'Aprobado', ['Modelo']))
        app.session_state[f'dev_panel_view_{self.project}'] = 'Reportes técnicos';app.run();self.clean(app)
        self.assertEqual(list(app.dataframe[0].value['Resultado']), ['Aprobado'])
        # Pinned, the model becomes a quick access on the project card; a click opens it with its own program.
        dj.set_pinned('link', report['links'][0]['id'], True)
        app.button(key='dev_panel_back').click().run();self.clean(app)
        with patch.object(local_files, '_launch') as launch:
            app.button(key=f"dev_quick_{self.project}_{report['links'][0]['id']}").click().run();self.clean(app)
            launch.assert_called_once_with(str(model))


if __name__ == '__main__':
    unittest.main()
