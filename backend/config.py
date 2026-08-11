"""配置管理模块（向后兼容过渡别名）。

配置管理已迁至 ``backend.services.system.config``。
旧的 ``from backend.config import X`` / ``from ..config import X`` 仍可用，
新代码请改用 ``from backend.services.system.config import X``。
"""
from .services.system import config as _config
import sys as _sys

# 让 ``backend.config`` 这个名字直接指向真正的配置模块，旧 import 路径零改动可用。
_sys.modules[__name__] = _config
