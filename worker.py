"""Proceso worker: corre APScheduler FUERA de los web workers de gunicorn.

En un deploy multi-proceso (gunicorn con varios workers, o réplicas en
Railway), si el scheduler arrancara en cada web worker el job diario se
dispararía N veces. Este proceso dedicado corre el scheduler UNA sola vez;
el/los proceso(s) web se despliegan con RUN_SCHEDULER=0.

Fuerza RUN_SCHEDULER=1 (su única razón de existir es correr el scheduler),
así el operador solo tiene que setear RUN_SCHEDULER=0 en el servicio web.
No sirve HTTP: create_app() arranca APScheduler en threads daemon y el
proceso se mantiene vivo bloqueando el thread principal.

Railway: agregar un servicio (o process type) con start command
`python worker.py`; setear RUN_SCHEDULER=0 en el servicio web (gunicorn).
El lock de corrida persistido (run_lock) sigue coordinando este scheduler
con las corridas manuales del Centro de Datos.
"""
import os

# ANTES de importar app.config (vía create_app): Config lee el entorno al
# importarse, así que el override tiene que estar seteado ya.
os.environ["RUN_SCHEDULER"] = "1"

import threading

from app import create_app

if __name__ == "__main__":
    create_app()   # arranca APScheduler (start_if_enabled si está enabled en DB)
    print("Worker de scheduler activo (APScheduler en background).", flush=True)
    threading.Event().wait()   # mantener vivo el proceso; los jobs corren en daemon threads
