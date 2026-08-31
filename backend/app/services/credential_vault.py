from __future__ import annotations

import ctypes
import hashlib
import os
from pathlib import Path
from ctypes import wintypes

from app.database import DATA_DIR


class CredentialVaultError(RuntimeError):
    pass


class CredentialVaultUnavailable(CredentialVaultError):
    pass


CRYPTPROTECT_UI_FORBIDDEN = 0x01
SECURE_DIR = DATA_DIR / "secure"


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def _reference_path(reference: str) -> Path:
    digest = hashlib.sha256(reference.encode("utf-8")).hexdigest()
    return SECURE_DIR / f"{digest}.bin"


def _blob_from_bytes(data: bytes) -> tuple[_DataBlob, ctypes.Array[ctypes.c_char]]:
    buffer = ctypes.create_string_buffer(data, len(data))
    blob = _DataBlob(
        cbData=len(data),
        pbData=ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)),
    )
    return blob, buffer


class WindowsDPAPICredentialVault:
    """Small local secret vault backed by Windows DPAPI.

    Ciphertext is stored under data/secure. DPAPI binds the encrypted blob to
    the current Windows user, so copying the file alone is not sufficient to
    recover the secret on another account or machine context.
    """

    backend_name = "windows_dpapi"

    def __init__(self) -> None:
        self._supported = os.name == "nt"
        self._crypt32 = None
        self._kernel32 = None
        if self._supported:
            self._crypt32 = ctypes.windll.crypt32
            self._kernel32 = ctypes.windll.kernel32

    @property
    def supported(self) -> bool:
        return self._supported

    def status(self) -> dict[str, object]:
        return {
            "supported": self.supported,
            "backend": self.backend_name,
        }

    def put_text(self, reference: str, value: str) -> None:
        if not value:
            raise CredentialVaultError("不能保存空凭据。")
        encrypted = self._protect(value.encode("utf-8"))
        path = _reference_path(reference)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(encrypted)
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        temporary.replace(path)

    def get_text(self, reference: str) -> str:
        path = _reference_path(reference)
        if not path.exists():
            raise CredentialVaultError("安全凭据不存在。")
        return self._unprotect(path.read_bytes()).decode("utf-8")

    def exists(self, reference: str) -> bool:
        return _reference_path(reference).exists()

    def delete(self, reference: str) -> bool:
        path = _reference_path(reference)
        if not path.exists():
            return False
        path.unlink()
        return True

    def _protect(self, data: bytes) -> bytes:
        if not self.supported or self._crypt32 is None or self._kernel32 is None:
            raise CredentialVaultUnavailable("当前系统不支持 Windows DPAPI 安全凭据存储。")

        input_blob, input_buffer = _blob_from_bytes(data)
        output_blob = _DataBlob()
        result = self._crypt32.CryptProtectData(
            ctypes.byref(input_blob),
            "Social Publisher",
            None,
            None,
            None,
            CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(output_blob),
        )
        _ = input_buffer
        if not result:
            raise CredentialVaultError("Windows DPAPI 加密失败。")
        try:
            return ctypes.string_at(output_blob.pbData, output_blob.cbData)
        finally:
            self._kernel32.LocalFree(output_blob.pbData)

    def _unprotect(self, data: bytes) -> bytes:
        if not self.supported or self._crypt32 is None or self._kernel32 is None:
            raise CredentialVaultUnavailable("当前系统不支持 Windows DPAPI 安全凭据存储。")

        input_blob, input_buffer = _blob_from_bytes(data)
        output_blob = _DataBlob()
        result = self._crypt32.CryptUnprotectData(
            ctypes.byref(input_blob),
            None,
            None,
            None,
            None,
            CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(output_blob),
        )
        _ = input_buffer
        if not result:
            raise CredentialVaultError("Windows DPAPI 解密失败，凭据可能已损坏或不属于当前 Windows 用户。")
        try:
            return ctypes.string_at(output_blob.pbData, output_blob.cbData)
        finally:
            self._kernel32.LocalFree(output_blob.pbData)


credential_vault = WindowsDPAPICredentialVault()


def account_secret_reference(account_id: int, kind: str) -> str:
    if kind not in {"password", "totp", "cookies"}:
        raise ValueError(f"unsupported account secret kind: {kind}")
    return f"social-publisher/account/{account_id}/{kind}"


def proxy_secret_reference(proxy_id: int, kind: str) -> str:
    if kind not in {"username", "password"}:
        raise ValueError(f"unsupported proxy secret kind: {kind}")
    return f"social-publisher/proxy/{proxy_id}/{kind}"


def clear_account_secrets(account_id: int) -> int:
    removed = 0
    for kind in ("password", "totp", "cookies"):
        removed += int(credential_vault.delete(account_secret_reference(account_id, kind)))
    return removed


def clear_proxy_secrets(proxy_id: int) -> int:
    removed = 0
    for kind in ("username", "password"):
        removed += int(credential_vault.delete(proxy_secret_reference(proxy_id, kind)))
    return removed
