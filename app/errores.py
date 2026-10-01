class ErrorDeNegocio(Exception):
    """Clase base para errores de reglas de negocio (no errores técnicos)."""


class DatosInvalidosException(ErrorDeNegocio):
    """Se lanza cuando faltan campos obligatorios o una cantidad no es positiva."""


class InventarioInsuficienteException(ErrorDeNegocio):
    """Se lanza cuando no hay existencia disponible suficiente (HU02, sección 6.1)."""
