# Pulpas de Fruta

Sistema web para digitalizar la gestión de pedidos, inventario y ventas de un negocio de venta de pulpas de fruta (proyecto de Ingeniería de Software).

![CI](https://github.com/Nicolas-Munera-J/Proyecto-Pulpas/actions/workflows/ci.yml/badge.svg)

**Integrantes:** Nicolás Múnera, Santiago Zuluaga, Isabela Castaño

## Estado del proyecto

Sprints 1 a 3 completos: base del sistema, usuarios e inventario (S1); registro y consulta de pedidos (S2); ciclo del pedido e inventario comprometido (S3).

- **HU20** – Inicio de sesión
- **HU21** – Cierre de sesión
- **HU13** – Registro de productos (catálogo)
- **HU14** – Consulta de existencias actuales
- **HU08** – Registro de entradas de inventario

**Sprint 2**

- **HU02** – Registro de pedido con verificación inmediata de inventario (`/pedidos/nuevo`)
- **HU09** – Alerta de posible pedido duplicado (misma pantalla)
- **HU01** – Consulta de pedidos del día (`/pedidos/hoy`)

**Sprint 3**

- **HU03** – Edición de un pedido antes de ser despachado (`/pedidos/<id>/editar`)
- **HU04** – Inventario comprometido sincronizado (`app/inventario/servicios.py`)
- **HU05** – Marcar pedido como despachado (botón en la vista diaria)
- **HU06** – Cancelación de un pedido (botón en la vista diaria)

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
- El **Gestor de pedidos** puede consultar existencias, registrar pedidos y ver los pedidos del día, pero recibe un error 403 si intenta registrar entradas.

Si ya tenías una base `pulpas.db` del Sprint 1, vuelve a ejecutar `python seed.py`: crea las tablas nuevas (`pedidos`, `detalles_pedido`) sin tocar los datos existentes.

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

**Pruebas del Sprint 2** (`tests/test_pedidos.py`):

| Historia | Qué verifican |
|---|---|
| HU02 | Pedido con inventario suficiente queda confirmado y compromete existencias (10 → 6 disponibles, 4 comprometidas) |
| HU02 | Sin inventario suficiente no se registra nada y no hay estado de espera |
| HU02 | Pedido con varios productos es todo-o-nada; líneas repetidas del mismo producto se suman |
| HU02 | Cantidades no positivas, campos obligatorios, fecha pasada y producto inactivo/inexistente se rechazan en el servidor |
| HU02 | De punta a punta por HTTP: registro correcto, error de inventario y cantidad no numérica |
| HU09 | Mismo cliente + mismos productos dentro de la ventana se marca como duplicado y no toca el inventario |
| HU09 | Distinto cliente, productos, fuera de ventana o pedido cancelado no es duplicado; si el gestor confirma, se registra |
| HU01 | Solo se listan pedidos confirmados con entrega hoy (no mañana, cancelados ni despachados); vista y mensaje de lista vacía |

**Pruebas del Sprint 3** (`tests/test_ciclo_pedido.py`):

| Historia | Qué verifican |
|---|---|
| HU06 | Cancelar libera lo comprometido (4 comprometidas → 10 disponibles, 0 comprometidas), con uno o varios productos; lo liberado se puede volver a vender |
| HU06 | No se cancela dos veces ni un pedido ya despachado |
| HU05 | Despachar registra fecha y hora y descuenta lo comprometido; no se despacha dos veces ni un cancelado; sale de los pedidos del día |
| HU03 | Aumentar/reducir cantidad ajusta solo la diferencia; quitar y agregar productos; sin inventario para el nuevo total no cambia nada (todo o nada) |
| HU03 | No se edita un pedido despachado o cancelado; validaciones en el servidor; conserva precios; pedido atrasado editable sin cambiar la fecha |
| HU04 | Tras cualquier secuencia de operaciones, lo comprometido en productos = suma de pedidos confirmados (`verificar_coherencia_inventario`); nunca quedan existencias negativas |
| Interfaz | Editar, despachar y cancelar por HTTP, 404 en pedidos inexistentes, redirección al login sin sesión, consulta de otra fecha |

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
│   ├── pedidos/               # HU02 / HU09 / HU01 (servicios.py = lógica de negocio, dtos.py)
│   ├── tiempo.py              # "hoy" en hora de Colombia (America/Bogota)
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

## Decisiones del Sprint 2

- **No existe estado de espera:** si no hay inventario, el pedido no se registra; si lo hay, queda `confirmado` y las unidades pasan de disponibles a comprometidas. El registro es todo-o-nada y el UPDATE de inventario es condicional para que dos pedidos simultáneos no comprometan la misma unidad.
- **Heurística de duplicado (HU09), pendiente de validar con el cliente:** mismo cliente (sin distinguir mayúsculas ni espacios) + mismo conjunto de productos + registrado hace menos de `VENTANA_DUPLICADO_MINUTOS` (30) + no cancelado. Las cantidades no se comparan. Es una advertencia, no un bloqueo: el gestor puede confirmar que es otro pedido.
- **"Hoy" en hora de Colombia:** el servidor y el CI corren en UTC; usar `date.today()` haría que después de las 7 p. m. los pedidos del día aparecieran vacíos.
- **Datos del cliente mínimos** (nombre y contacto opcional) por la Ley 1581 de 2012; no hay tabla de clientes.
- `precio_unitario` y `fecha_despacho` se guardan desde ya para HU10 y HU05, así no hay que alterar tablas después.

## Decisiones del Sprint 3

- **Despachar descuenta lo comprometido.** El documento solo dice que HU05 cambia el estado y registra fecha y hora, pero la sección 6.3 define existencia física = disponible + comprometida. Si al despachar no se descontara, la fruta que ya salió seguiría contando como existencia. Por eso despachar baja `comprometida` (y `disponible` no cambia: ya estaba descontada al confirmar).
- **Editar verifica solo las unidades adicionales.** Un pedido de 4 que pasa a 9 necesita 5 más disponibles, no 9. El ajuste es por diferencia y todo o nada.
- **Un pedido despachado o cancelado no se edita, despacha ni cancela.** Los cambios de estado usan un UPDATE condicional (`WHERE estado = 'confirmado'`), así que dos clics simultáneos no mueven el inventario dos veces.
- **Coherencia verificable.** `verificar_coherencia_inventario()` compara lo comprometido con la suma de los pedidos confirmados; las pruebas la ejecutan después de cada escenario (mitigación de R-006).
- **La vista diaria acepta `?fecha=AAAA-MM-DD`** para poder editar, despachar o cancelar pedidos de otros días; el historial completo es HU07 (Sprint 5).
- **Sin confirmación de pago ni totales todavía:** la forma de pago al despachar (HU11) llega en el Sprint 4.

## Trabajo colaborativo

Una rama por historia (`feature/hu08-entradas-inventario`), integración a `main` mediante pull request revisado y aprobado por otro integrante, y pipeline en verde antes de fusionar.

## Nota de uso de inteligencia artificial

Se utilizó Claude (Anthropic) como herramienta de apoyo durante el proyecto: estructurar la documentación, formalizar el flujo de pedidos y, en este taller, redactar una primera versión del workflow de CI, de las pruebas automatizadas y del README. La idea de negocio, la problemática y las decisiones de diseño son del equipo. Todo el contenido generado fue revisado, ejecutado y ajustado por los integrantes antes de aceptarlo, y el código generado se audita con el chequeo de código limpio y seguro del proyecto.

## Pendiente para próximos sprints

- Sprint 4: totales automáticos, forma de pago y reportes (HU10, HU11, HU17, HU18). HU11 se registra al despachar: habrá que ampliar `despachar_pedido`.
- Protección CSRF en los formularios que modifican datos (despachar, cancelar, editar, registrar): hoy ninguno la tiene. Va en el chequeo de código seguro.
- Validar con el cliente la heurística de duplicados de HU09 (ventana de 30 minutos).
