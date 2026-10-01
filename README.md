# Pulpas de Fruta

Sistema web para digitalizar la gestión de pedidos, inventario y ventas de un negocio de venta de pulpas de fruta (proyecto de Ingeniería de Software).

![CI](https://github.com/Nicolas-Munera-J/Proyecto-Pulpas/actions/workflows/ci.yml/badge.svg)

**Integrantes:** Nicolás Múnera, Santiago Zuluaga, Isabela Castaño

## Estado del proyecto

Sprint 1 completo: base del sistema, usuarios e inventario.

- **HU20** – Inicio de sesión
- **HU21** – Cierre de sesión
- **HU13** – Registro de productos (catálogo)
- **HU14** – Consulta de existencias actuales
- **HU08** – Registro de entradas de inventario

**Historia del taller de integración continua: HU08.** El administrador registra una entrada de inventario (producto, cantidad, observación) y la existencia disponible aumenta. Ruta: `/inventario/entradas` · lógica: `app/inventario/servicios.py` · datos: tablas `productos` y `movimientos_inventario`.

## Requisitos

- Python 3.14 (la misma versión que usa el pipeline; ver `.github/workflows/ci.yml`)
- Git

## Cómo levantar el proyecto desde cero

```bash
git clone https://github.com/Nicolas-Munera-J/Proyecto-Pulpas.git
cd Proyecto-Pulpas

python -m venv venv
source venv/bin/activate        # en Windows: venv\Scripts\activate

pip install -r requirements.txt

python seed.py                  # crea la base de datos y los usuarios de prueba
python run.py                   # servidor en http://127.0.0.1:5000
```

`seed.py` crea la base de datos local (`pulpas.db`) con dos usuarios y tres productos de ejemplo.

**Usuarios de demostración** (solo para probar el sistema en local; no son credenciales reales):

| Rol | Correo | Contraseña |
|---|---|---|
| Administrador | admin@pulpas.com | admin123 |
| Gestor de pedidos | gestor@pulpas.com | gestor123 |

- El **Administrador** puede registrar productos y entradas de inventario (HU13, HU08).
- El **Gestor de pedidos** puede consultar existencias, pero recibe un error 403 si intenta registrar entradas.

Para un despliegue real, la clave de sesiones se define con la variable de entorno `SECRET_KEY` y las contraseñas de los usuarios de demostración se cambian. Nunca se suben claves reales, tokens ni archivos `.env` al repositorio (ver `.gitignore`).

## Cómo correr las pruebas

Con el entorno virtual activado y las dependencias instaladas:

```bash
pytest
```

Las pruebas usan una base de datos SQLite en memoria; no tocan `pulpas.db`. Cubren HU08:

| Prueba | Qué verifica |
|---|---|
| `test_entrada_incrementa_existencia_y_registra_movimiento` | Criterio de aceptación: dado 10 unidades, cuando entran 5, entonces quedan 15 y se guarda el movimiento |
| `test_entrada_con_cantidad_no_positiva_se_rechaza` | Cantidades 0 y negativas se rechazan y no cambian la existencia |
| `test_entrada_para_producto_inexistente_se_rechaza` | Un producto que no existe lanza el error de negocio |
| `test_administrador_registra_entrada_desde_la_interfaz` | De punta a punta por HTTP: login como administrador y POST a `/inventario/entradas` |
| `test_gestor_de_pedidos_no_puede_registrar_entradas` | El servidor responde 403 al gestor (autorización por rol) |
| `test_sin_sesion_se_redirige_al_login` | Sin sesión se redirige a `/login` |

## Pipeline de integración continua

El archivo `.github/workflows/ci.yml` se ejecuta en cada `push` y `pull request`. Tiene dos trabajos:

1. **test**: instala dependencias con `pip install -r requirements.txt` y ejecuta `pytest`.
2. **auditoria-dependencias**: ejecuta `pip-audit` sobre `requirements.txt` para detectar vulnerabilidades conocidas.

Estado actual: ver la pestaña **Actions** del repositorio o la insignia de arriba.

## Estructura del proyecto

```
├── .github/workflows/ci.yml   # pipeline de CI
├── app/
│   ├── __init__.py            # application factory
│   ├── extensions.py          # db, bcrypt, login_manager
│   ├── models.py              # Usuario, Producto, MovimientoInventario
│   ├── errores.py             # excepciones de negocio propias
│   ├── auth/                  # HU20 / HU21
│   ├── productos/             # HU13
│   ├── inventario/            # HU08 / HU14 (servicios.py = lógica de negocio)
│   ├── main/                  # dashboard
│   ├── templates/
│   └── static/css/
├── tests/                     # pruebas automatizadas (pytest)
├── config.py
├── pytest.ini
├── run.py
├── seed.py
└── requirements.txt
```

## Decisiones de diseño

- Nombres de entidades y variables en español de dominio (`existencia_disponible`, `existencia_comprometida`, `umbral_minimo`).
- La lógica de negocio vive en funciones separadas de las rutas (`inventario/servicios.py`); cada función hace una sola cosa.
- Los errores de negocio se manejan con excepciones propias (`app/errores.py`), nunca con un `except` vacío.
- Las contraseñas se guardan con hash bcrypt, nunca en texto plano (RNF03).
- Cada ruta protegida valida el rol **en el servidor** con `@requiere_administrador`, no solo ocultando botones.
- El acceso a datos se hace con SQLAlchemy ORM, sin concatenar SQL a mano.

## Trabajo colaborativo

Una rama por historia (`feature/hu08-entradas-inventario`), integración a `main` mediante pull request revisado y aprobado por otro integrante, y pipeline en verde antes de fusionar.

## Nota de uso de inteligencia artificial

Se utilizó Claude (Anthropic) como herramienta de apoyo durante el proyecto: estructurar la documentación, formalizar el flujo de pedidos y, en este taller, redactar una primera versión del workflow de CI, de las pruebas automatizadas y del README. La idea de negocio, la problemática y las decisiones de diseño son del equipo. Todo el contenido generado fue revisado, ejecutado y ajustado por los integrantes antes de aceptarlo, y el código generado se audita con el chequeo de código limpio y seguro del proyecto.

## Pendiente para próximos sprints

- Sprint 2: registro y consulta de pedidos (HU01, HU02, HU09).
- Definir la heurística de "proximidad horaria" antes de implementar la detección de pedidos duplicados (HU09).
