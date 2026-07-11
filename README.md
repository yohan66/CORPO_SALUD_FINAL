# Sistema de Bienes Nacionales CORPO_SALUD

Sistema web de gestión de bienes nacionales para la  Corporación de Salud del Estado Táchira.
## Características

- **Consultar Bienes**: Búsqueda y filtrado por código, nombre, categoría y estado
- **Agregar Bienes**: Registro de nuevos bienes con validación
- **Modificar Bienes**: Edición de información de bienes existentes
- **Eliminar Bienes**: Baja de bienes con registro de movimientos
- **Reporte Mensual**: Estadísticas y reportes en formato CSV

## Instalación

```bash
# Clonar o copiar el proyecto
cd bienes_unet

# Ejecutar el servidor
python3 app.py
```

O usar el script:
```bash
./run.sh
```

## Credenciales por defecto

- **Usuario**: `admin`
- **Contraseña**: `admin123`

## Estructura

```
bienes CORPO_SALUD/
├── app.py           # Servidor HTTP con API REST
├── bienes_unet.db   # Base de datos SQLite
├── run.sh           # Script de ejecución
├── templates/
│   ├── index.html   # Página principal
│   └── login.html   # Página de login
└── static/
    └── css/
        └── styles.css
```

## API Endpoints

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/bienes` | GET | Listar bienes (con paginación y filtros) |
| `/api/bienes` | POST | Crear nuevo bien |
| `/api/bienes/{id}` | GET | Obtener bien por ID |
| `/api/bienes/{id}` | PUT | Actualizar bien |
| `/api/bienes/{id}` | DELETE | Eliminar bien |
| `/api/bienes/categorias` | GET | Listar categorías |
| `/api/bienes.csv` | GET | Exportar bienes a CSV |
| `/api/reporte-mensual` | GET | Reporte mensual |
| `/api/reporte-mensual.csv` | GET | Reporte mensual en CSV |

## Uso

1. Iniciar el servidor: `python3 app.py`
2. Abrir navegador en: `http://localhost:5000`
3. Iniciar sesión con las credenciales
4. Navegar entre las pestañas usando el menú superior
