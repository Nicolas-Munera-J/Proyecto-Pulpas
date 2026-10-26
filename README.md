# Pulpas de Fruta

Sistema web para digitalizar la gestión de pedidos, inventario y ventas de un negocio de venta de pulpas de fruta (proyecto de Ingeniería de Software).

![CI](https://github.com/Nicolas-Munera-J/Proyecto-Pulpas/actions/workflows/ci.yml/badge.svg)

**Integrantes:** Nicolás Múnera, Santiago Zuluaga, Isabela Castaño

## Estado del proyecto

Sprints 1 a 5 completos: base del sistema, usuarios e inventario (S1); registro y consulta de pedidos (S2); ciclo del pedido e inventario comprometido (S3); totales, formas de pago y reportes (S4); historial, existencias bajas, mermas, exportación y gestión de usuarios (S5).

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

**Sprint 4**

- **HU10** – Cálculo automático del total del pedido (vista de pedidos y vista previa en el formulario)
- **HU11** – Registro de la forma de pago al despachar
- **HU17** – Reporte de ventas por periodo (`/reportes/ventas`, solo administrador)
- **HU18** – Productos más vendidos (`/reportes/productos-mas-vendidos`, solo administrador)

**Sprint 5**

- **HU07** – Búsqueda y consulta del historial de pedidos (`/pedidos/historial`)
- **HU15** – Alerta de existencias bajas (aviso al tomar pedidos y mermas, filtro en existencias)
- **HU16** – Registro de mermas por daño o vencimiento (`/inventario/mermas`, solo administrador)
- **HU19** – Exportar el reporte de ventas a CSV (`/reportes/ventas/exportar`, solo administrador)
- **HU22** – Gestión de usuarios: crear, asignar rol, desactivar y reactivar (`/usuarios`, solo administrador)
- **Protección CSRF** en todos los formularios que modifican datos (`app/seguridad.py`). No es una historia del backlog: se agregó porque HU22 la volvía crítica.

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

**Si ya tenías una base `pulpas.db` de un sprint anterior, vuelve a ejecutar `python seed.py`.** Crea las tablas nuevas y agrega las columnas nuevas a las tablas existentes: `pedidos.forma_pago` (Sprint 4) y `movimientos_inventario.motivo` (Sprint 5); `create_all()` por sí solo no agrega columnas. No borra datos y se puede ejecutar varias veces. Los pedidos despachados antes del Sprint 4 quedan con forma de pago "sin registrar" en los reportes.

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

**Pruebas del Sprint 4** (`tests/test_ventas_reportes.py`):

| Historia | Qué verifican |
|---|---|
| HU10 | Total = suma de cantidad × precio (2 × $8.500 + 3 × $9.000 = $44.000); se recalcula al editar; un cambio de precio en el catálogo no altera pedidos ya tomados; formato en pesos |
| HU11 | Despachar guarda la forma de pago; sin forma de pago válida (vacía, nula, desconocida) se rechaza sin cambiar estado ni inventario; flujo por HTTP |
| HU17 | Solo cuentan los pedidos despachados; respeta el rango de fechas; el periodo se mide en hora de Colombia (venta de las 11:30 p. m. cuenta ese día); desglose por forma de pago; periodo inválido; precios históricos |
| HU18 | Orden de mayor a menor cantidad, suma entre pedidos, excluye no despachados, desempate por nombre, respeta el periodo |
| Seguridad | Los reportes devuelven 403 al gestor de pedidos y redirigen al login sin sesión (el rol se valida en el servidor) |
| Migración | Agrega `forma_pago` a una base del Sprint 3 sin perder datos y es idempotente |

**Pruebas del Sprint 5**

| Archivo | Historia | Qué verifican |
|---|---|---|
| `test_historial_pedidos.py` | HU07 | Filtros por estado, canal, rango de fechas (inclusive) y nombre sin distinguir mayúsculas; los comodines `%` y `_` se buscan como texto; filtros combinados e inválidos; paginación con páginas fuera de rango; vista HTTP |
| `test_stock_mermas.py` | HU15 | Stock bajo en el umbral exacto; solo productos activos; aviso en el mismo mensaje al tomar o editar un pedido; filtro "solo stock bajo"; umbral predeterminado en productos nuevos |
| `test_stock_mermas.py` | HU16 | La merma descuenta lo disponible y registra motivo y usuario; no se pueden descartar unidades comprometidas ni más de lo disponible; no rompe la coherencia del inventario; solo administrador; migración de `motivo` |
| `test_exportar_ventas.py` | HU19 | Resumen, desglose por forma de pago y detalle; periodo en hora de Colombia; tildes y ñ; neutraliza fórmulas de Excel en nombres de clientes (`=`, `+`, `-`, `@`); descarga con cabeceras correctas; solo administrador |
| `test_usuarios.py` | HU22 | Alta con hash de contraseña y correo normalizado; validaciones; correo único; el usuario creado entra y su rol limita el acceso; cambio de rol; desactivar cierra la sesión abierta y conserva el historial; nunca queda sin administrador activo; nadie se desactiva a sí mismo; el gestor no puede darse permisos |
| `test_seed_demo.py` | Demo | Los datos de demostración son coherentes con el inventario; los reportes tienen historia; los ejemplos del guion (pedido nuevo, duplicado, sin inventario, alerta de stock bajo, editar, despachar, cancelar, merma) producen los resultados esperados |
| `test_seguridad_csrf.py` | CSRF | POST sin token o con token falso → 400 y sin cambios; con token (campo o cabecera) funciona; el token es distinto por sesión; **todos** los formularios POST de la aplicación llevan el token (prueba de seguridad contra olvidos futuros) |

## Datos de demostración

Para presentar el sistema con historia (y no con la base vacía) existe `seed_demo.py`:

```bash
python seed_demo.py --reiniciar     # BORRA pulpas.db y carga la demo
```

Carga 6 productos con entradas de inventario, 13 ventas despachadas en los últimos 10 días (efectivo, transferencia y tarjeta), 4 pedidos confirmados para hoy y 2 para mañana, 2 pedidos cancelados, 3 mermas y 4 usuarios (uno desactivado). Mango y Fresa quedan en stock bajo para mostrar la alerta. Todo se crea con las mismas funciones de la aplicación, así que el inventario queda coherente con los pedidos; `tests/test_seed_demo.py` lo verifica y comprueba los ejemplos del guion de la presentación. **Es solo para demostración: no lo ejecuten sobre datos reales.**

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
│   ├── usuarios/              # HU22 (servicios.py = reglas de usuarios y roles)
│   ├── reportes/              # HU17 / HU18 / HU19 (servicios.py = consultas, cálculos y CSV)
│   ├── seguridad.py           # protección CSRF
│   ├── tiempo.py              # "hoy" y rangos de fechas en hora de Colombia (America/Bogota)
│   ├── formato.py             # formato de pesos para las plantillas
│   ├── migraciones.py         # agrega columnas nuevas a bases ya creadas (lo usa seed.py)
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

## Decisiones del Sprint 4

- **Una venta es un pedido despachado.** Los confirmados aún no se entregan ni se cobran, y los cancelados nunca se vendieron. El periodo de los reportes se mide por la fecha y hora de despacho, no por la de entrega ni la de registro. *Pendiente de validar con el cliente.*
- **Los periodos usan hora de Colombia.** Las fechas se guardan en UTC; una venta despachada a las 11:30 p. m. ya es del día siguiente en UTC, así que se convierte el rango antes de consultar.
- **Los totales usan el precio guardado en cada línea (`precio_unitario`)**, no el del catálogo. Cambiar un precio no altera pedidos ni ventas ya realizadas. En una edición, las líneas que ya existían conservan su precio y las líneas nuevas entran al precio vigente.
- **Formas de pago:** efectivo, transferencia, tarjeta y otro. No incluí "crédito/fiado" porque el documento no lo menciona. *Si el negocio vende a crédito, hay que validarlo con el cliente.*
- **Los reportes son solo del Administrador**, como indica la sección 4 del documento; el rol se valida en cada endpoint.
- **Despachar exige forma de pago:** la pantalla la pide con un selector antes de confirmar y el servidor la valida.
- **Migración sencilla en lugar de Alembic:** `app/migraciones.py` agrega la columna nueva a bases existentes. Si el proyecto sigue creciendo conviene adoptar Alembic.

## Decisiones del Sprint 5

- **HU07:** las fechas del historial son la fecha de **entrega** (la misma de la vista diaria); también se busca por nombre del cliente. *Pendiente de validar con el cliente.* Lo usan ambos roles.
- **HU15:** la regla "stock bajo" (`disponible <= umbral`, ya existente desde el Sprint 1) se mantiene: el aviso aparece cuando la existencia **llega** al umbral, no solo cuando lo supera hacia abajo. El umbral de cada producto sigue siendo propio; `UMBRAL_STOCK_BAJO_PREDETERMINADO = 5` es el valor que se propone al crear un producto (antes era 0, lo que dejaba la alerta inservible). La alerta va dentro del mismo aviso de "pedido registrado" porque varios avisos seguidos se pisan en pantalla.
- **HU16:** una merma solo descuenta existencia **disponible**. Las unidades comprometidas por pedidos confirmados no se pueden descartar: hay que editar o cancelar el pedido primero. Solo administrador, como indica la sección 4 del documento.
- **HU19:** CSV con separador `;` y BOM UTF-8, para que Excel en español (Colombia) lo abra en columnas y con tildes. Los valores van en pesos enteros, igual que en pantalla. Los textos que empiezan por `=`, `+`, `-` o `@` se prefijan con una comilla para evitar la inyección de fórmulas. Si se prefiere `.xlsx`, habría que agregar `openpyxl`.
- **HU22:** los usuarios no se borran, se desactivan, para conservar quién registró cada pedido. Siempre debe quedar un administrador activo y nadie puede desactivar su propia cuenta. Desactivar cierra la sesión abierta de inmediato. Contraseña mínima de 8 caracteres, guardada solo como hash.
- **Protección CSRF:** token por sesión exigido en todo POST. En `tests/conftest.py` se desactiva (`CSRF_ACTIVADO = False`) para no repetir el token en cada prueba; `test_seguridad_csrf.py` la activa y verifica que ningún formulario la omita. Si agregan un formulario nuevo, incluyan `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`.

## Trabajo colaborativo

Una rama por historia (`feature/hu08-entradas-inventario`), integración a `main` mediante pull request revisado y aprobado por otro integrante, y pipeline en verde antes de fusionar.

## Nota de uso de inteligencia artificial

Se utilizó Claude (Anthropic) como herramienta de apoyo durante el proyecto: estructurar la documentación, formalizar el flujo de pedidos y, en este taller, redactar una primera versión del workflow de CI, de las pruebas automatizadas y del README. La idea de negocio, la problemática y las decisiones de diseño son del equipo. Todo el contenido generado fue revisado, ejecutado y ajustado por los integrantes antes de aceptarlo, y el código generado se audita con el chequeo de código limpio y seguro del proyecto.

## Pendiente para próximos sprints

- Backlog completo implementado (Sprints 1 a 5). Lo que queda son los pendientes del chequeo de código limpio y seguro: comentarios del "porqué" (decisión de no tener estado de espera), consultas con ORM revisadas una vez más, cumplimiento de la Ley 1581 de 2012, y análisis de dependencias (`pip-audit`) y de logs en el pipeline.
- Fuera de HU22 y no implementado: restablecer la contraseña de un usuario (hoy, si alguien la olvida, hay que desactivarlo y crear otro usuario). Conviene pedirlo al cliente.
- El cierre de sesión (`/logout`) sigue siendo un enlace GET, sin token CSRF: lo peor que permite es cerrar una sesión.
- Validar con el cliente la heurística de duplicados de HU09 (ventana de 30 minutos).
