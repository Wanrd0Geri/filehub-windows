"""Preview-only, deterministic image output numbering; never publishes files."""
import os
import re
from pathlib import Path

from ..models import checked_path
from ..naming import validate_component


def _key(path):
    return str(Path(os.path.abspath(path))).casefold()


def allocate_conversion_target(desired, *, reserved=(), own_source=None):
    """Keep an available name, otherwise advance after its numbered family max.

    own_source permits only this conversion's exact same-path replacement.
    Callers must exclude its own input from reserved, but never other inputs.
    No reservation is mutated here: callers commit only successful previews.
    """
    desired = checked_path(desired)
    validate_component(desired.name)
    reserved = tuple(Path(path) for path in reserved)
    names = [path.name for path in reserved if _key(path.parent) == _key(desired.parent)]
    on_disk = list(desired.parent.iterdir()) if desired.parent.is_dir() else []
    own = own_source is not None and _key(desired) == _key(own_source)
    occupied = {name.casefold() for name in names}
    occupied.update(path.name.casefold() for path in on_disk
                    if not (own and _key(path) == _key(desired)))
    if desired.name.casefold() not in occupied:
        return desired
    match = re.fullmatch(r'(.*)-([0-9]+)', desired.stem)
    base, digits = (match.group(1), match.group(2)) if match else (desired.stem, '')
    # Bound parsing and probing so pathological external names cannot stall UI.
    if len(digits) > 18:
        raise ValueError('图片编号过长，请调整文件名')
    maximum = int(digits) if digits else 0
    family = re.compile(re.escape(base.casefold()) + r'-([0-9]+)' + re.escape(desired.suffix.casefold()))
    for name in occupied:
        numbered = family.fullmatch(name)
        if numbered:
            suffix = numbered.group(1)
            if len(suffix) > 18:
                raise ValueError('图片编号过长，请调整文件名')
            maximum = max(maximum, int(suffix))
    for number in range(maximum + 1, maximum + 10001):
        name = validate_component(f'{base}-{str(number).zfill(len(digits))}{desired.suffix}')
        if name.casefold() not in occupied:
            return checked_path(desired.with_name(name))
    raise ValueError('无法分配图片编号，请重新预览')
