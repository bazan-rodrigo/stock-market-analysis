"""Servidor de desarrollo (Windows). No usar en producción."""

if __name__ == "__main__":
    from app import create_app

    _, dash_app = create_app()

    dash_app.run(
        debug=True,
        host="0.0.0.0",
        port=8080,
        use_reloader=False,
    )
