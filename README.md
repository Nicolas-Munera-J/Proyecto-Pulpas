# Pulpas de Fruta — Sprint 1

Base del sistema, usuarios e inventario.

## Historias cubiertas

- **HU20** – Inicio de sesión
- **HU21** – Cierre de sesión
- **HU13** – Registro de productos (catálogo)
- **HU14** – Consulta de existencias actuales
- **HU08** – Registro de entradas de inventario

## Cómo correrlo

```bash
python -m venv venv
source venv/bin/activate   # en Windows: venv\Scripts\activate

pip install -r requirements.txt

python seed.py    # crea la base de datos y usuarios de prueba
python run.py      # levanta el servidor en http://127.0.0.1:5000
```

**Usuarios de prueba** (creados por `seed.py`):

| Rol         | Correo             | Contraseña |
|-------------|---------------------|------------|
| Administrador | admin@pulpas.com  | admin123   |
| Gestor de pedidos | gestor@pulpas.com | gestor123  |

## Estructura del proyecto

```
proyecto_pulpas/
├── app/
│   ├── __init__.py          # application factory
│   ├── extensions.py        # db, bcrypt, login_manager
│   ├── models.py            # Usuario, Producto, MovimientoInventario
│   ├── errores.py           # excepciones de negocio propias
│   ├── auth/                # HU20 / HU21
│   ├── productos/           # HU13
│   ├── inventario/          # HU08 / HU14 (servicios.py = lógica de negocio)
│   ├── main/                # dashboard
│   ├── templates/
│   └── static/css/
├── config.py
├── run.py
├── seed.py
└── requirements.txt
```

## Decisiones de diseño aplicadas del documento del proyecto

- Los nombres de variables y entidades usan el dominio en español (`existenciaDisponible`,
  `existenciaComprometida`, `umbralMinimo`) tal como se definió en la sección de código limpio.
- La verificación de inventario y el registro de movimientos están separados en funciones
  distintas dentro de `inventario/servicios.py` — no una sola función que hace todo.
- Los errores de negocio (cantidad inválida, producto inexistente) se manejan con
  excepciones propias (`app/errores.py`), nunca con un `except` vacío.
- Las contraseñas se guardan con hash (bcrypt), nunca en texto plano (RNF03).
- Cada ruta protegida valida el rol **en el servidor** con el decorador
  `@requiere_administrador`, no solo ocultando botones en el HTML.

## Pendiente para próximos sprints

- Sprint 2: registro y consulta de pedidos (HU01, HU02, HU09).
- La detección de "posible pedido duplicado" (HU09) todavía no está definida a nivel
  de heurística concreta — hay que decidir el criterio de "proximidad horaria" antes
  de implementarla.
- Consultas parametrizadas ya están cubiertas por el uso de SQLAlchemy ORM en todo
  el proyecto (evita concatenar SQL a mano).
