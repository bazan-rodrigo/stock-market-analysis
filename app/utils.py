import functools
import logging

logger = logging.getLogger(__name__)


def safe_callback(on_error):
    """
    Decorador para callbacks Dash que captura cualquier excepción no manejada
    y retorna los valores de error definidos por el caller.

    Debe aplicarse entre @callback y def (es decir, justo encima de def):

        @callback(
            Output("my-alert", "children"),
            Output("my-alert", "is_open"),
            Output("my-alert", "color"),
        )
        @safe_callback(lambda exc: (f"Error inesperado: {exc}", True, "danger"))
        def my_callback(...):
            ...

    on_error: callable(exc: Exception) → retorno del mismo shape que el callback normal.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                logger.exception("Error en callback '%s'", func.__name__)
                return on_error(exc)
        return wrapper
    return decorator
