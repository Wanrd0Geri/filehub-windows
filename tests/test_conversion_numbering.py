from pathlib import Path
import pytest

from filehub.conversion.naming import allocate_conversion_target


@pytest.mark.parametrize('desired,occupied,expected', [
    ('图片-6.png', ['图片-6.png'], '图片-7.png'),
    ('图片-006.png', ['图片-006.png', '图片-019.png'], '图片-020.png'),
    ('a_20261001.jpg', ['A_20261001.JPG', 'a_20261001-8.jpg'], 'a_20261001-9.jpg'),
    ('a.jpeg.jpg', ['a.jpeg.jpg'], 'a.jpeg-1.jpg'),
    ('a.jpg', ['a-9.jpg'], 'a.jpg'),
    ('Straße-6.png', ['Straße-6.png', 'STRASSE-9.PNG'], 'Straße-10.png'),
])
def test_collision_family_only_allocates_when_needed(tmp_path, desired, occupied, expected):
    for name in occupied:
        (tmp_path/name).mkdir()
    assert allocate_conversion_target(tmp_path/desired) == tmp_path/expected


def test_casefold_reservations_and_own_replacement(tmp_path):
    desired = tmp_path/'image.png'
    desired.write_bytes(b'original')
    assert allocate_conversion_target(desired, reserved=[tmp_path/'IMAGE-12.PNG']) == tmp_path/'image-13.png'
    assert allocate_conversion_target(desired, own_source=desired) == desired
    assert allocate_conversion_target(desired, reserved=[desired], own_source=desired) == tmp_path/'image-1.png'
