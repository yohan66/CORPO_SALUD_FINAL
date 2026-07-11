#!/usr/bin/env python3
import http.server
import socketserver
import sqlite3
import json
import urllib.parse
import re
import html
import secrets
from datetime import datetime

PORT = 5000
DB_FILE = 'CORPO_SALUD.db'
SECRET_KEY = 'CORPO_SALUD_bienes_nacionales_2026'
SESSIONS = {}


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


class BienesHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == '/':
            if not self.is_authenticated():
                self.send_response(302)
                self.send_header('Location', '/login')
                self.end_headers()
                return
            self.send_html('templates/index.html')
        elif path == '/login':
            self.send_html('templates/login.html')
        elif path == '/logout':
            self.send_response(302)
            self.send_header('Location', '/login')
            self.send_header('Set-Cookie', 'session=; Path=/; HttpOnly; Max-Age=0')
            self.end_headers()
        elif path.startswith('/api/'):
            if not self.is_authenticated():
                self.send_json({'success': False, 'error': 'No autorizado. Inicie sesión.'}, 401)
                return
            self.handle_api(query)
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == '/login':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8')
            params = urllib.parse.parse_qs(post_data)
            self.handle_login(params)
        elif path.startswith('/api/'):
            if not self.is_authenticated():
                self.send_json({'success': False, 'error': 'No autorizado. Inicie sesión.'}, 401)
                return
            data = self.read_json_body()
            self.handle_api_write(path, data)
        else:
            self.send_response(404)
            self.end_headers()

    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path.startswith('/api/'):
            if not self.is_authenticated():
                self.send_json({'success': False, 'error': 'No autorizado. Inicie sesión.'}, 401)
                return
            data = self.read_json_body()
            self.handle_api_write(path, data)
        else:
            self.send_response(404)
            self.end_headers()

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path.startswith('/api/'):
            if not self.is_authenticated():
                self.send_json({'success': False, 'error': 'No autorizado. Inicie sesión.'}, 401)
                return
            self.handle_api_delete(path)
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def read_json_body(self):
        content_length = int(self.headers.get('Content-Length', 0))
        if not content_length:
            return {}
        post_data = self.rfile.read(content_length).decode('utf-8')
        try:
            return json.loads(post_data)
        except ValueError:
            return {}

    def handle_login(self, params):
        usuario = params.get('usuario', [''])[0]
        contrasena = params.get('contrasena', [''])[0]
        db = get_db()
        user = db.execute('SELECT * FROM usuarios WHERE usuario = ? AND contrasena = ?',
                          (usuario, contrasena)).fetchone()
        db.close()

        if not user:
            self.send_html('templates/login.html', error='Credenciales inválidas')
            return

        token = secrets.token_urlsafe(32)
        SESSIONS[token] = {
            'usuario': user['usuario'],
            'nombre': user['nombre'] or user['usuario'],
            'rol': user['rol'] or 'usuario'
        }

        self.send_response(302)
        self.send_header('Location', '/')
        self.send_header('Set-Cookie', f'session={token}; Path=/; HttpOnly; SameSite=Lax')
        self.end_headers()

    def handle_api(self, query):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == '/api/bienes':
            self.send_bienes_list(query)
        elif path == '/api/bienes.csv':
            self.send_bienes_csv(query)
        elif path == '/api/bienes/categorias':
            self.send_categorias()
        elif path.startswith('/api/bienes/'):
            parts = path.split('/')
            if len(parts) == 4 and parts[3].isdigit():
                self.send_bien(int(parts[3]))
            else:
                self.send_json({'success': False, 'error': 'Ruta inválida'}, 400)
        elif path == '/api/reporte-mensual':
            self.send_reporte_mensual(query, guardar=True)
        elif path == '/api/reporte-mensual.csv':
            self.send_reporte_mensual(query, guardar=True, as_csv=True)
        elif path == '/api/estadisticas':
            self.send_estadisticas()
        else:
            self.send_json({'success': False, 'error': 'Ruta no encontrada'}, 404)

    def send_bienes_list(self, query):
        db = get_db()
        sql, params = build_bienes_sql(query, paginated=True)
        count_sql = sql.replace('SELECT *', 'SELECT COUNT(*)')
        total = db.execute(count_sql, params).fetchone()[0]

        page = int(query.get('page', ['1'])[0])
        per_page = int(query.get('per_page', ['50'])[0])
        offset = (page - 1) * per_page
        sql += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
        params.extend([per_page, offset])

        bienes = db.execute(sql, params).fetchall()
        db.close()
        self.send_json({
            'bienes': [dict(b) for b in bienes],
            'total': total,
            'page': page,
            'per_page': per_page
        })

    def send_categorias(self):
        db = get_db()
        categorias = db.execute('SELECT DISTINCT categoria FROM bienes WHERE categoria IS NOT NULL AND categoria != "" ORDER BY categoria').fetchall()
        db.close()
        self.send_json([c['categoria'] for c in categorias])

    def send_bien(self, bien_id):
        db = get_db()
        bien = db.execute('SELECT * FROM bienes WHERE id = ?', (bien_id,)).fetchone()
        db.close()
        if bien:
            self.send_json(dict(bien))
        else:
            self.send_json({'success': False, 'error': 'Bien no encontrado'}, 404)

    def send_bienes_csv(self, query):
        db = get_db()
        sql, params = build_bienes_sql(query, paginated=False)
        sql += ' ORDER BY created_at DESC'
        rows = db.execute(sql, params).fetchall()
        db.close()

        columns = [
            'codigo', 'nombre', 'descripcion', 'categoria', 'fecha_ingreso',
            'costo', 'estado', 'ubicacion', 'responsable', 'observaciones'
        ]
        csv_rows = [columns]
        for row in rows:
            csv_rows.append([row.get(col) for col in columns])

        self.send_csv(csv_rows, 'bienes.csv')

    def send_estadisticas(self):
        db = get_db()
        total = db.execute('SELECT COUNT(*) FROM bienes').fetchone()[0]
        activos = db.execute('SELECT COUNT(*) FROM bienes WHERE estado = "Activo"').fetchone()[0]
        por_categoria = db.execute('''
            SELECT categoria, COUNT(*) as cantidad
            FROM bienes
            WHERE categoria IS NOT NULL AND categoria != ""
            GROUP BY categoria ORDER BY cantidad DESC
        ''').fetchall()
        db.close()

        self.send_json({
            'total': total,
            'activos': activos,
            'inactivos': total - activos,
            'por_categoria': [dict(c) for c in por_categoria]
        })

    def send_reporte_mensual(self, query, guardar=False, as_csv=False):
        data = build_reporte_data(query)

        if guardar:
            db = get_db()
            db.execute('''
                INSERT OR REPLACE INTO reportes_mensuales
                (mes, anio, fecha_generacion, total_bienes, bienes_nuevos, bienes_dados_baja, usuario)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                data['mes'], data['anio'], data['fecha_generacion'],
                data['total_bienes'], data['bienes_nuevos'], data['bienes_dados_baja'],
                self.get_session_value('usuario')
            ))
            db.commit()
            db.close()

        if as_csv:
            self.send_reporte_csv(data)
        else:
            self.send_json(data)

    def handle_api_write(self, path, data):
        if path == '/api/bienes':
            self.create_bien(data)
        elif path.startswith('/api/bienes/'):
            parts = path.split('/')
            if len(parts) == 4 and parts[3].isdigit():
                self.update_bien(int(parts[3]), data)
            else:
                self.send_json({'success': False, 'error': 'Ruta inválida'}, 400)
        else:
            self.send_json({'success': False, 'error': 'Ruta no encontrada'}, 404)

    def handle_api_delete(self, path):
        parts = path.split('/')
        if not (len(parts) == 4 and parts[3].isdigit()):
            self.send_json({'success': False, 'error': 'Ruta inválida'}, 400)
            return

        bien_id = int(parts[3])
        db = get_db()
        bien = db.execute('SELECT * FROM bienes WHERE id = ?', (bien_id,)).fetchone()
        if not bien:
            db.close()
            self.send_json({'success': False, 'error': 'Bien no encontrado'}, 404)
            return

        db.execute('''
            INSERT INTO movimientos (bien_id, tipo_movimiento, fecha, usuario, descripcion)
            VALUES (?, ?, ?, ?, ?)
        ''', (bien_id, 'Eliminación', datetime.now().strftime('%Y-%m-%d'), self.get_session_value('usuario'), 'Bien eliminado'))

        db.execute('DELETE FROM bienes WHERE id = ?', (bien_id,))
        db.commit()
        db.close()
        self.send_json({'success': True, 'message': 'Bien eliminado exitosamente'})

    def create_bien(self, data):
        codigo = data.get('codigo', '').strip()
        nombre = data.get('nombre', '').strip()

        if not codigo or not nombre:
            self.send_json({'success': False, 'error': 'El código y el nombre son obligatorios'}, 400)
            return

        db = get_db()
        try:
            cursor = db.execute('''
                INSERT INTO bienes
                (codigo, nombre, descripcion, categoria, fecha_ingreso, costo, estado, ubicacion, responsable, observaciones)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                codigo,
                nombre,
                data.get('descripcion', '').strip(),
                data.get('categoria', '').strip(),
                data.get('fecha_ingreso') or datetime.now().strftime('%Y-%m-%d'),
                float(data.get('costo') or 0),
                data.get('estado') or 'Activo',
                data.get('ubicacion', '').strip(),
                data.get('responsable', '').strip(),
                data.get('observaciones', '').strip()
            ))
            bien_id = cursor.lastrowid
            db.execute('''
                INSERT INTO movimientos (bien_id, tipo_movimiento, fecha, usuario, descripcion)
                VALUES (?, ?, ?, ?, ?)
            ''', (bien_id, 'Registro', datetime.now().strftime('%Y-%m-%d'), self.get_session_value('usuario'), 'Bien registrado'))
            db.commit()
            db.close()
            self.send_json({'success': True, 'id': bien_id, 'message': 'Bien registrado exitosamente'})
        except sqlite3.IntegrityError:
            db.close()
            self.send_json({'success': False, 'error': 'El código del bien ya existe'}, 400)

    def update_bien(self, bien_id, data):
        db = get_db()
        bien = db.execute('SELECT * FROM bienes WHERE id = ?', (bien_id,)).fetchone()
        if not bien:
            db.close()
            self.send_json({'success': False, 'error': 'Bien no encontrado'}, 404)
            return

        codigo = data.get('codigo', '').strip()
        nombre = data.get('nombre', '').strip()
        if not codigo or not nombre:
            db.close()
            self.send_json({'success': False, 'error': 'El código y el nombre son obligatorios'}, 400)
            return

        try:
            db.execute('''
                UPDATE bienes SET
                    codigo = ?, nombre = ?, descripcion = ?, categoria = ?,
                    fecha_ingreso = ?, costo = ?, estado = ?, ubicacion = ?,
                    responsable = ?, observaciones = ?, updated_at = ?
                WHERE id = ?
            ''', (
                codigo,
                nombre,
                data.get('descripcion', '').strip(),
                data.get('categoria', '').strip(),
                data.get('fecha_ingreso') or bien['fecha_ingreso'],
                float(data.get('costo') or 0),
                data.get('estado') or bien['estado'],
                data.get('ubicacion', '').strip(),
                data.get('responsable', '').strip(),
                data.get('observaciones', '').strip(),
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                bien_id
            ))
            db.execute('''
                INSERT INTO movimientos (bien_id, tipo_movimiento, fecha, usuario, descripcion)
                VALUES (?, ?, ?, ?, ?)
            ''', (bien_id, 'Modificación', datetime.now().strftime('%Y-%m-%d'), self.get_session_value('usuario'), 'Bien modificado'))
            db.commit()
            db.close()
            self.send_json({'success': True, 'message': 'Bien actualizado exitosamente'})
        except sqlite3.IntegrityError:
            db.close()
            self.send_json({'success': False, 'error': 'El código del bien ya existe'}, 400)

    def send_reporte_csv(self, data):
        rows = [
            ['Reporte Mensual de Bienes', data['mes'], data['anio']],
            [],
            ['Total Bienes', data['total_bienes']],
            ['Bienes Nuevos', data['bienes_nuevos']],
            ['Dados de Baja', data['bienes_dados_baja']],
            ['Activos', data['bienes_activos']],
            ['Inactivos', data['bienes_inactivos']],
            [],
            ['Bienes por Categoría'],
            ['Categoria', 'Cantidad']
        ]
        rows.extend([[c['categoria'], c['cantidad']] for c in data['por_categoria']])
        rows.append([])
        rows.append(['Bienes Registrados en el Mes'])
        rows.append(['Codigo', 'Nombre', 'Categoria', 'Fecha', 'Costo'])
        rows.extend([[
            b['codigo'], b['nombre'], b.get('categoria') or '', b['fecha_ingreso'], b.get('costo') or ''
        ] for b in data['bienes_mes']])
        rows.append([])
        rows.append(['Movimientos del Mes'])
        rows.append(['Fecha', 'Tipo', 'Codigo', 'Nombre', 'Usuario', 'Descripcion'])
        rows.extend([[
            m.get('fecha') or '', m.get('tipo_movimiento') or '', m.get('codigo') or '',
            m.get('nombre') or '', m.get('usuario') or '', m.get('descripcion') or ''
        ] for m in data['movimientos_mes']])

        self.send_csv(rows, f"reporte_mensual_{data['anio']}_{data['mes']:02d}.csv")

    def send_csv(self, rows, filename):
        lines = []
        for row in rows:
            lines.append(','.join(csv_escape(value) for value in row))
        content = '\n'.join(lines).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/csv; charset=utf-8')
        self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def send_html(self, filepath, error=None):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except FileNotFoundError:
            self.send_response(404)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(b'<h1>404 - Archivo no encontrado</h1>')
            return

        if filepath == 'templates/login.html':
            if error:
                error_html = f'<div class="message error">{html.escape(error, quote=True)}</div>'
                content = re.sub(r'\{% if error %\}.*?\{% endif %\}', error_html, content, flags=re.S)
            else:
                content = re.sub(r'\{% if error %\}.*?\{% endif %\}', '', content, flags=re.S)
        elif filepath == 'templates/index.html':
            session = self.get_session()
            content = content.replace('{{ url_for(\'static\', filename=\'css/styles.css\') }}', '/static/css/styles.css')
            content = content.replace('{{ url_for(\'logout\') }}', '/logout')
            content = content.replace('{{ session.nombre }}', html.escape(session['nombre'], quote=True) if session else 'Usuario')
            content = content.replace('{{ session.rol }}', html.escape(session['rol'], quote=True) if session else 'usuario')
            content = content.replace('{{ current_year }}', str(datetime.now().year))

        body = content.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def get_cookie(self, name):
        cookie_header = self.headers.get('Cookie', '')
        for part in cookie_header.split(';'):
            if '=' not in part:
                continue
            key, value = part.strip().split('=', 1)
            if key == name:
                return value
        return ''

    def is_authenticated(self):
        token = self.get_cookie('session')
        return token in SESSIONS

    def get_session(self):
        token = self.get_cookie('session')
        return SESSIONS.get(token)

    def get_session_value(self, key):
        session = self.get_session()
        if not session:
            return 'Sistema'
        return session.get(key) or 'Sistema'


def get_db():
    db = sqlite3.connect(DB_FILE)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    db = get_db()
    db.executescript('''
        CREATE TABLE IF NOT EXISTS bienes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT UNIQUE NOT NULL,
            nombre TEXT NOT NULL,
            descripcion TEXT,
            categoria TEXT,
            fecha_ingreso TEXT NOT NULL,
            costo REAL,
            estado TEXT DEFAULT 'Activo',
            ubicacion TEXT,
            responsable TEXT,
            observaciones TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS movimientos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bien_id INTEGER NOT NULL,
            tipo_movimiento TEXT NOT NULL,
            fecha TEXT NOT NULL,
            usuario TEXT,
            descripcion TEXT,
            FOREIGN KEY (bien_id) REFERENCES bienes(id)
        );

        CREATE TABLE IF NOT EXISTS reportes_mensuales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mes INTEGER NOT NULL,
            anio INTEGER NOT NULL,
            fecha_generacion TEXT NOT NULL,
            total_bienes INTEGER DEFAULT 0,
            bienes_nuevos INTEGER DEFAULT 0,
            bienes_dados_baja INTEGER DEFAULT 0,
            usuario TEXT,
            UNIQUE(mes, anio)
        );

        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE NOT NULL,
            contrasena TEXT NOT NULL,
            nombre TEXT,
            rol TEXT DEFAULT 'usuario'
        );

        INSERT OR IGNORE INTO usuarios (usuario, contrasena, nombre, rol)
        VALUES ('admin', 'admin123', 'Administrador', 'admin');
    ''')
    db.commit()
    db.close()


def build_bienes_sql(query, paginated=True):
    sql = 'SELECT * FROM bienes WHERE 1=1'
    params = []

    search = query.get('search', [''])[0]
    if search:
        sql += ' AND (codigo LIKE ? OR nombre LIKE ? OR descripcion LIKE ? OR categoria LIKE ?)'
        params.extend([f'%{search}%', f'%{search}%', f'%{search}%', f'%{search}%'])

    estado = query.get('estado', [''])[0]
    if estado:
        sql += ' AND estado = ?'
        params.append(estado)

    categoria = query.get('categoria', [''])[0]
    if categoria:
        sql += ' AND categoria = ?'
        params.append(categoria)

    return sql, params


def build_reporte_data(query):
    mes = int(query.get('mes', [datetime.now().month])[0])
    anio = int(query.get('anio', [datetime.now().year])[0])
    inicio_mes = f'{anio}-{mes:02d}-01'
    fin_mes = f'{anio + 1}-01-01' if mes == 12 else f'{anio}-{mes + 1:02d}-01'

    db = get_db()
    total_bienes = db.execute('SELECT COUNT(*) FROM bienes WHERE fecha_ingreso < ?', (fin_mes,)).fetchone()[0]
    bienes_nuevos = db.execute('''
        SELECT COUNT(*) FROM bienes
        WHERE fecha_ingreso >= ? AND fecha_ingreso < ?
    ''', (inicio_mes, fin_mes)).fetchone()[0]
    bienes_activos = db.execute('SELECT COUNT(*) FROM bienes WHERE estado = "Activo" AND fecha_ingreso < ?', (fin_mes,)).fetchone()[0]
    bienes_inactivos = db.execute('SELECT COUNT(*) FROM bienes WHERE estado != "Activo" AND fecha_ingreso < ?', (fin_mes,)).fetchone()[0]
    bienes_dados_baja = db.execute('''
        SELECT COUNT(*) FROM movimientos
        WHERE tipo_movimiento = "Eliminación" AND fecha >= ? AND fecha < ?
    ''', (inicio_mes, fin_mes)).fetchone()[0]

    por_categoria = db.execute('''
        SELECT categoria, COUNT(*) as cantidad
        FROM bienes
        WHERE fecha_ingreso < ? AND categoria IS NOT NULL AND categoria != ""
        GROUP BY categoria ORDER BY cantidad DESC
    ''', (fin_mes,)).fetchall()
    bienes_mes = db.execute('''
        SELECT * FROM bienes
        WHERE fecha_ingreso >= ? AND fecha_ingreso < ?
        ORDER BY fecha_ingreso DESC
    ''', (inicio_mes, fin_mes)).fetchall()
    movimientos_mes = db.execute('''
        SELECT m.*, b.codigo, b.nombre
        FROM movimientos m
        JOIN bienes b ON m.bien_id = b.id
        WHERE m.fecha >= ? AND m.fecha < ?
        ORDER BY m.fecha DESC
    ''', (inicio_mes, fin_mes)).fetchall()
    db.close()

    return {
        'mes': mes,
        'anio': anio,
        'fecha_generacion': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_bienes': total_bienes,
        'bienes_nuevos': bienes_nuevos,
        'bienes_dados_baja': bienes_dados_baja,
        'bienes_activos': bienes_activos,
        'bienes_inactivos': bienes_inactivos,
        'por_categoria': [dict(c) for c in por_categoria],
        'bienes_mes': [dict(b) for b in bienes_mes],
        'movimientos_mes': [dict(m) for m in movimientos_mes]
    }


def csv_escape(value):
    if value is None:
        text = ''
    else:
        text = str(value)
    if ',' in text or '"' in text or '\n' in text or '\r' in text:
        return '"' + text.replace('"', '""') + '"'
    return text


if __name__ == '__main__':
    init_db()
    with ReusableTCPServer(('', PORT), BienesHandler) as httpd:
        print(f'Servidor corriendo en http://localhost:{PORT}')
        print('Usuario: admin | Contraseña: admin123')
        print('Presione Ctrl+C para detener')
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('\nServidor detenido')
            httpd.shutdown()
