import os
import signal
from typing import Dict, ForwardRef, List, Optional

import toml
from pydantic import BaseSettings, Field, validator

DEFAULT_IGNORES = [
    # Some of these are redundant
    '.git/*', '__pycache__/*', '.*',
    '.tox/*', '.venv/*', '.pytest_cache/*'
]

ForemonConfig = ForwardRef('ForemonConfig')


class ForemonConfig(BaseSettings):

    alias:           str = Field('')

    ################################
    # Script execution
    ################################
    cwd:             str = Field(os.getcwd())
    environment:     Dict = Field(default_factory=dict)
    returncode:      int = Field(0)
    scripts:         List[str] = Field(default_factory=list)
    term_signal:     int = Field(int(signal.SIGTERM))

    ################################
    # Change monitoring
    ################################
    ignore_case:     bool = Field(True)
    ignore_defaults: List[str] = Field(DEFAULT_IGNORES)
    ignore_dirs:     bool = Field(True)
    ignore:          List[str] = Field(default_factory=list)
    paths:           List[str] = Field(['.'])
    patterns:        List[str] = Field(['*'])
    recursive:       bool = Field(True)

    configs:         List[ForemonConfig] = Field(default_factory=list)

    @validator('term_signal', pre=True)
    def validate_term_signal(cls, value) -> int:
        if isinstance(value, str):
            if hasattr(signal.Signals, value):
                value = getattr(signal.Signals, value)
        return int(value)

    class Config:
        env_prefix = 'foremon_'
        # we mutate objects while parsing objects to handle sub-configs
        extra = 'forbid'
        anystr_strip_whitespace = True

    def __init__(self, *args, **kwargs):
        configs = kwargs.get('configs', [])
        kwargs['configs'] = configs

        for name in list(kwargs.keys()):
            if name in self.__fields__:
                continue

            # extra fields that are dicts are treated as configs
            if not isinstance(kwargs[name], dict):
                continue

            obj = kwargs.pop(name)

            obj['alias'] = name
            configs.append(obj)
        super().__init__(*args, **kwargs)


ForemonConfig.update_forward_refs()


class ToolsConfig(BaseSettings):

    foremon: Optional[ForemonConfig]

    class Config:
        extra = 'allow'


class PyProjectConfig(BaseSettings):

    tools: ToolsConfig = Field(default_factory=ToolsConfig)

    class Config:
        extra = 'allow'

    @classmethod
    def parse_toml(cls, text: str) -> 'PyProjectConfig':
        data = toml.loads(text)
        project = cls.parse_obj(data)
        return project


__all__ = ['PyProjectConfig', 'ToolsConfig', 'ForemonConfig']