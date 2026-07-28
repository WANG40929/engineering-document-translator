"""Built-in user-interface language catalogs.

The catalogs live in Python modules so they are included automatically by
setuptools and PyInstaller without requiring separate package-data rules.
"""

from __future__ import annotations

from .de import TRANSLATIONS as DE
from .en import TRANSLATIONS as EN
from .es import TRANSLATIONS as ES
from .fr import TRANSLATIONS as FR
from .ru import TRANSLATIONS as RU
from .zh_cn import TRANSLATIONS as ZH_CN


CATALOGS = {
    "zh-CN": ZH_CN,
    "en": EN,
    "ru": RU,
    "es": ES,
    "fr": FR,
    "de": DE,
}

SUPPORTED_LANGUAGE_CODES = tuple(CATALOGS)
