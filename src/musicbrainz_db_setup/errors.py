from __future__ import annotations


class ExitCode:
    OK = 0
    USER_ERROR = 1
    NETWORK = 2
    CHECKSUM = 3
    SQL = 4
    COPY = 5
    SIGINT = 130


class MBSetupError(Exception):
    exit_code: int = ExitCode.USER_ERROR


class UserError(MBSetupError):
    exit_code = ExitCode.USER_ERROR


class NetworkError(MBSetupError):
    exit_code = ExitCode.NETWORK


class ChecksumError(MBSetupError):
    exit_code = ExitCode.CHECKSUM


class SchemaError(MBSetupError):
    exit_code = ExitCode.SQL


class ImportError_(MBSetupError):
    exit_code = ExitCode.COPY


class PrerequisiteMissing(UserError):
    pass
