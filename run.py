"""Servidor de desarrollo. No usar en producción."""
import sys
import traceback

if __name__ == "__main__":
    print("Iniciando create_app()...", flush=True)
    try:
        from app import create_app
        _, dash_app = create_app()
    except Exception:
        print("ERROR FATAL durante create_app():", flush=True)
        traceback.print_exc()
        sys.exit(1)

    print(f"App lista. Servidor en http://0.0.0.0:8050", flush=True)
    dash_app.run(
        debug=True,
        host="0.0.0.0",
        port=8050,
        use_reloader=False,
    )
