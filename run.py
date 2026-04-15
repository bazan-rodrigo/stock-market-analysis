"""Servidor de desarrollo (Windows). No usar en producción."""

if __name__ == "__main__":
    from app import create_app

    _, dash_app = create_app()

    dash_app.run(
        debug=True,
        host="0.0.0.0",
        port=8050,
        use_reloader=True,
        # Excluir logs para que los cambios en el archivo de log
        # no disparen un reinicio del servidor
        exclude_patterns=["logs*", "*.log"],
    )
