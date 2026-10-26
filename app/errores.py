class ErrorDeNegocio(Exception):
    """Clase base para errores de reglas de negocio (no errores técnicos)."""


class DatosInvalidosException(ErrorDeNegocio):
    """Se lanza cuando faltan campos obligatorios o una cantidad no es positiva."""


class InventarioInsuficienteException(ErrorDeNegocio):
    """Se lanza cuando no hay existencia disponible suficiente (HU02, sección 6.1).

    `faltantes` lista, por producto, lo solicitado y lo disponible, para que
    la interfaz pueda explicar exactamente qué no alcanza.
    """

    def __init__(self, mensaje: str, faltantes=None):
        super().__init__(mensaje)
        self.faltantes = faltantes or []


class PedidoPosiblementeDuplicadoException(ErrorDeNegocio):
    """HU09 - Se lanza cuando el pedido se parece a uno registrado hace poco.

    No es un rechazo definitivo: el gestor puede confirmar que sí es un
    pedido distinto y registrarlo de todos modos.
    """

    def __init__(self, mensaje: str, pedido_existente):
        super().__init__(mensaje)
        self.pedido_existente = pedido_existente


class TransicionDePedidoInvalidaException(ErrorDeNegocio):
    """HU03/HU05/HU06 - Se lanza al intentar editar, despachar o cancelar un
    pedido que ya no está confirmado (despachado o cancelado)."""
