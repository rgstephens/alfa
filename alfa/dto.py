import socket
from typing import Any, Dict, List, Union

from pydantic import BaseModel as BM
from pydantic import BaseSettings, Field

from .const import StrEnum


class BaseDTO(BM):
    pass


class UnknownError(BaseDTO):
    class ErrorCode(StrEnum):
        UNKNOWN = 'unknown'

    code: ErrorCode


class InvalidRequestError(BaseDTO):
    class ErrorCode(StrEnum):
        INVALID_REQUEST = 'invalid_request'

    code: ErrorCode
    details: List[Dict[str, Any]]


class BusinessError(BaseDTO):
    class ErrorCode(StrEnum):
        pass

    code: ErrorCode


class LooseBaseDTO(BaseDTO):
    class Config:
        extra = 'ignore'


class StrictBaseDTO(BaseDTO):
    class Config:
        extra = 'forbid'


errors: Dict[Union[int, str], Dict[str, Any]] = {
    400: {'model': InvalidRequestError},
    422: {'model': BusinessError},
    500: {'model': UnknownError},
}


class ReadyResp(StrictBaseDTO):
    class ServiceCheck(StrictBaseDTO):
        service: str
        is_ready: bool
        error: str

    is_ready: bool
    checks: List[ServiceCheck]


class Version(BaseSettings):
    git_branch: str = Field('git_branch', env='GIT_BRANCH')
    git_short_hash: str = Field('git_short_hash', env='GIT_HASH')
    build_date: str = Field('build_date', env='BUILD_DATE')
    build_number: str = Field('build_number', env='BUILD_NUMBER')

    def get_version(self) -> str:
        return f'{self.git_branch}-{self.build_number}'

    def get_instance_id(self) -> str:
        return socket.gethostname()


class VersionResp(Version):
    pass
