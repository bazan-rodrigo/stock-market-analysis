import time

_cache: dict = {"public_access": False, "_expires": 0.0}
_TTL = 30  # segundos


def _load() -> bool:
    from app.database import get_session
    from app.models import AppSetting
    try:
        row = get_session().query(AppSetting).filter_by(id=1).first()
        return bool(row.public_access) if row else False
    except Exception:
        return False


def is_public_access_enabled() -> bool:
    now = time.monotonic()
    if now >= _cache["_expires"]:
        _cache["public_access"] = _load()
        _cache["_expires"] = now + _TTL
    return _cache["public_access"]


def set_public_access(enabled: bool) -> None:
    from app.database import get_session
    from app.models import AppSetting
    s = get_session()
    row = s.query(AppSetting).filter_by(id=1).first()
    if row is None:
        row = AppSetting(id=1, public_access=enabled)
        s.add(row)
    else:
        row.public_access = enabled
    s.commit()
    _cache["public_access"] = enabled
    _cache["_expires"] = time.monotonic() + _TTL
