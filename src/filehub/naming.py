"""Finite, non-evaluating naming tokens with strict Windows output validation."""
import re
from collections.abc import Mapping

NAMING_TOKENS = frozenset({'original', 'stem', 'ext', 'prefix', 'note', 'date',
                           'date_long', 'period', 'episode', 'scene', 'shot',
                           'sequence', 'resolution'})
_TOKEN = re.compile(r'\{([a-z_]+)\}')
_DEVICE = re.compile(r'^(CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³])$', re.I)


def validate_component(name: str) -> str:
    if not isinstance(name, str) or not name or name in ('.', '..') or name.endswith((' ', '.')):
        raise ValueError('名称不能为空、包含路径穿越或以空格/点结尾')
    if _DEVICE.fullmatch(name.split('.', 1)[0].rstrip(' ')):
        raise ValueError('名称是 Windows 保留设备名')
    if any(c in '\\/:*?"<>|' or ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in name):
        raise ValueError('名称包含非法 Windows 字符')
    if len(name.encode('utf-16-le')) // 2 > 255:
        raise ValueError('名称超过 255 UTF-16 单元')
    return name


def validate_pattern(pattern: str, allowed_tokens=NAMING_TOKENS) -> str:
    if not isinstance(pattern, str) or not pattern:
        raise ValueError('命名模板不能为空')
    tokens = _TOKEN.findall(pattern)
    remainder = _TOKEN.sub('', pattern)
    if '{' in remainder or '}' in remainder:
        raise ValueError('命名模板仅支持 {token}，不支持格式、访问或表达式')
    if any(token not in allowed_tokens for token in tokens):
        raise ValueError('命名模板包含未知 token')
    # Use a real extension to accept {ext} alone and reject CON{ext}. Actual
    # values (including absent optional values) are validated again at render.
    sample = _TOKEN.sub(lambda m: '.png' if m[1] == 'ext' else 'x', pattern)
    validate_component(sample)
    return pattern


def render_pattern(pattern: str, values: Mapping) -> str:
    validate_pattern(pattern)
    def value(match):
        token = match[1]
        result = values.get(token, '')
        if result is None: result = ''
        if token == 'sequence' and (not isinstance(result, int) or isinstance(result, bool) or result < 0):
            raise ValueError('sequence 必须是非负整数')
        return str(result)
    return validate_component(_TOKEN.sub(value, pattern))
