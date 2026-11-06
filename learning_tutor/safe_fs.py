"""Conservative identity-bound filesystem mutation helpers."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PathIdentity:
    device: int
    inode: int


@dataclass(frozen=True)
class ParentIdentity:
    path: Path
    identity: PathIdentity


@dataclass(frozen=True)
class TrackedDirectory:
    path: Path
    identity: PathIdentity


class IdentityMismatchError(OSError):
    """A pathname no longer identifies the object authorized for mutation."""


def status_identity(status: os.stat_result) -> PathIdentity:
    return PathIdentity(status.st_dev, status.st_ino)


def path_identity(path: Path) -> PathIdentity:
    return status_identity(path.stat(follow_symlinks=False))


def has_identity(path: Path, identity: PathIdentity) -> bool:
    try:
        return path_identity(path) == identity
    except OSError:
        return False


def track_directory(path: Path) -> TrackedDirectory:
    status = path.stat(follow_symlinks=False)
    if _is_reparse_or_symlink(status) or not stat.S_ISDIR(status.st_mode):
        raise IdentityMismatchError(f"tracked path is not a plain directory: {path}")
    return TrackedDirectory(path, status_identity(status))


def _is_reparse_or_symlink(status: os.stat_result) -> bool:
    attributes = getattr(status, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(status.st_mode) or bool(attributes & reparse_flag)


def capture_parent_chain(root: Path, destination: Path) -> tuple[ParentIdentity, ...]:
    try:
        relative_parent = destination.parent.relative_to(root)
    except ValueError as error:
        raise IdentityMismatchError(
            f"mutation parent escapes trusted root: {destination.parent}"
        ) from error
    chain: list[ParentIdentity] = []
    current = root
    for part in (".", *relative_parent.parts):
        if part != ".":
            current /= part
        status = current.stat(follow_symlinks=False)
        if _is_reparse_or_symlink(status) or not stat.S_ISDIR(status.st_mode):
            raise IdentityMismatchError(
                f"mutation parent is not a plain directory: {current}"
            )
        chain.append(ParentIdentity(current, status_identity(status)))
    return tuple(chain)


def verify_parent_chain(
    root: Path,
    destination: Path,
    expected: tuple[ParentIdentity, ...],
) -> None:
    if capture_parent_chain(root, destination) != expected:
        raise IdentityMismatchError(
            f"mutation parent identity changed: {destination.parent}"
        )


def _supports_bound_mkdir() -> bool:
    return (
        os.mkdir in os.supports_dir_fd
        and os.stat in os.supports_dir_fd
        and hasattr(os, "O_DIRECTORY")
    )


def _open_verified_parent(parent: ParentIdentity) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(parent.path, flags)
    if status_identity(os.fstat(descriptor)) != parent.identity:
        os.close(descriptor)
        raise IdentityMismatchError(
            f"directory changed while opening handle: {parent.path}"
        )
    return descriptor


def _open_windows_path(
    path: Path,
    identity: PathIdentity,
    *,
    directory: bool,
    delete: bool = False,
) -> int:
    """Open a non-delete-share Windows handle and verify its identity."""

    import ctypes
    import msvcrt
    from ctypes import wintypes

    create_file = ctypes.WinDLL("kernel32", use_last_error=True).CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    handle = create_file(
        str(path),
        0x0080
        | (0x00000001 if directory else 0)  # READ_ATTRIBUTES | LIST_DIRECTORY
        | (0x00010000 if delete else 0),  # DELETE
        0x00000001 | 0x00000002,  # FILE_SHARE_READ | FILE_SHARE_WRITE
        None,
        3,  # OPEN_EXISTING
        (0x02000000 if directory else 0)
        | 0x00200000,  # BACKUP_SEMANTICS | OPEN_REPARSE_POINT
        None,
    )
    invalid_handle = wintypes.HANDLE(-1).value
    if handle == invalid_handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY)
    except BaseException:
        ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(handle)
        raise
    status = os.fstat(descriptor)
    if status_identity(status) != identity:
        os.close(descriptor)
        raise IdentityMismatchError(
            f"path changed while opening Windows handle: {path}"
        )
    if directory != stat.S_ISDIR(status.st_mode):
        os.close(descriptor)
        raise IdentityMismatchError(f"path type changed while opening Windows handle: {path}")
    return descriptor


def _open_windows_directory(parent: ParentIdentity) -> int:
    return _open_windows_path(parent.path, parent.identity, directory=True)


def _lock_windows_chain(chain: tuple[ParentIdentity, ...]) -> list[int]:
    descriptors: list[int] = []
    try:
        for parent in chain:
            descriptors.append(_open_windows_directory(parent))
        return descriptors
    except BaseException:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        raise


def _before_bound_replace(source: Path, destination: Path) -> None:
    """Narrow race-test hook after parent capture and before mutation."""


def _windows_handle_rename_no_replace(
    source_fd: int,
    destination: Path,
) -> None:
    """Rename the object named by source_fd without replacing a destination."""

    import ctypes
    import msvcrt
    from ctypes import wintypes

    class FileRenameInfo(ctypes.Structure):
        _fields_ = (
            ("ReplaceIfExists", wintypes.BOOLEAN),
            ("RootDirectory", wintypes.HANDLE),
            ("FileNameLength", wintypes.DWORD),
            ("FileName", wintypes.WCHAR * 1),
        )

    destination_name = str(destination)
    encoded_length = len(destination_name.encode("utf-16-le"))
    size = ctypes.sizeof(FileRenameInfo) + encoded_length
    buffer = ctypes.create_string_buffer(size)
    info = FileRenameInfo.from_buffer(buffer)
    info.ReplaceIfExists = False
    info.RootDirectory = None
    info.FileNameLength = encoded_length
    ctypes.memmove(
        ctypes.addressof(buffer) + FileRenameInfo.FileName.offset,
        destination_name.encode("utf-16-le"),
        encoded_length,
    )
    set_information = ctypes.WinDLL(
        "kernel32", use_last_error=True
    ).SetFileInformationByHandle
    set_information.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    )
    set_information.restype = wintypes.BOOL
    if not set_information(
        msvcrt.get_osfhandle(source_fd),
        3,  # FileRenameInfo
        buffer,
        size,
    ):
        error = ctypes.get_last_error()
        if error in (80, 183):  # ERROR_FILE_EXISTS / ERROR_ALREADY_EXISTS
            raise FileExistsError(error, os.strerror(error), destination_name)
        raise ctypes.WinError(error)


def identity_bound_replace(
    source: Path,
    destination: Path,
    *,
    root: Path,
    expected_source: PathIdentity | None = None,
) -> PathIdentity:
    """Move a verified source without replacing any destination.

    Windows supplies a source-handle-bound rename.  POSIX rename APIs bind
    parent traversal but cannot bind the final source entry to an already
    verified inode, so this operation conservatively refuses there.
    """

    identity = path_identity(source) if expected_source is None else expected_source
    source_chain = capture_parent_chain(root, source)
    destination_chain = capture_parent_chain(root, destination)
    source_fd: int | None = None
    destination_fd: int | None = None
    windows_locks: list[int] = []
    try:
        if os.name != "nt":
            raise IdentityMismatchError(
                "POSIX cannot prove a source-identity-bound no-replace rename; "
                "source and destination were preserved"
            )
        windows_locks.extend(_lock_windows_chain(source_chain))
        windows_locks.extend(_lock_windows_chain(destination_chain))
        _before_bound_replace(source, destination)
        verify_parent_chain(root, source, source_chain)
        verify_parent_chain(root, destination, destination_chain)
        source_fd = _open_windows_path(
            source,
            identity,
            directory=stat.S_ISDIR(source.stat(follow_symlinks=False).st_mode),
            delete=True,
        )
        destination_fd = windows_locks[-1]
        _windows_handle_rename_no_replace(
            source_fd,
            destination,
        )
        verify_parent_chain(root, destination, destination_chain)
        if path_identity(destination) != identity:
            raise IdentityMismatchError(
                f"destination identity changed after rename: {destination}"
            )
        return identity
    finally:
        if source_fd is not None:
            os.close(source_fd)
        if destination_fd is not None and destination_fd not in windows_locks:
            os.close(destination_fd)
        for descriptor in reversed(windows_locks):
            os.close(descriptor)


def _before_bound_mkdir(path: Path) -> None:
    """Narrow race-test hook after parent capture and before creation."""


def identity_bound_mkdir(path: Path, *, root: Path) -> TrackedDirectory:
    """Create one directory through a verified parent when supported."""

    parent_chain = capture_parent_chain(root, path)
    parent_fd: int | None = None
    windows_locks: list[int] = []
    try:
        if _supports_bound_mkdir():
            parent_fd = _open_verified_parent(parent_chain[-1])
        elif os.name == "nt":
            windows_locks.extend(_lock_windows_chain(parent_chain))
        else:
            raise IdentityMismatchError(
                "filesystem does not support identity-bound directory creation"
            )
        _before_bound_mkdir(path)
        verify_parent_chain(root, path, parent_chain)
        if parent_fd is None:
            path.mkdir()
        else:
            os.mkdir(path.name, dir_fd=parent_fd)
        verify_parent_chain(root, path, parent_chain)
        return track_directory(path)
    finally:
        if parent_fd is not None:
            os.close(parent_fd)
        for descriptor in reversed(windows_locks):
            os.close(descriptor)


def _before_identity_cleanup(directory: TrackedDirectory) -> None:
    """Narrow race-test hook before destructive cleanup."""


def _before_windows_handle_delete(path: Path) -> None:
    """Race-test hook after a Windows object is bound to a delete handle."""


def _windows_mark_delete(descriptor: int) -> None:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    class FileDispositionInfo(ctypes.Structure):
        _fields_ = (("DeleteFile", wintypes.BOOL),)

    info = FileDispositionInfo(True)
    set_information = ctypes.WinDLL(
        "kernel32", use_last_error=True
    ).SetFileInformationByHandle
    set_information.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    )
    set_information.restype = wintypes.BOOL
    if not set_information(
        msvcrt.get_osfhandle(descriptor),
        4,  # FileDispositionInfo
        ctypes.byref(info),
        ctypes.sizeof(info),
    ):
        raise ctypes.WinError(ctypes.get_last_error())


def _windows_delete_bound_tree(path: Path, descriptor: int) -> None:
    """Delete a tree through non-delete-share handles from leaf to root."""

    _before_windows_handle_delete(path)
    for entry in os.scandir(path):
        child = Path(entry.path)
        child_status = child.stat(follow_symlinks=False)
        if _is_reparse_or_symlink(child_status):
            child_is_directory = False
        else:
            child_is_directory = stat.S_ISDIR(child_status.st_mode)
        child_descriptor = _open_windows_path(
            child,
            status_identity(child_status),
            directory=child_is_directory,
            delete=True,
        )
        try:
            if child_is_directory:
                _windows_delete_bound_tree(child, child_descriptor)
            else:
                _before_windows_handle_delete(child)
            _windows_mark_delete(child_descriptor)
        finally:
            os.close(child_descriptor)
    _windows_mark_delete(descriptor)


def remove_tracked_tree(directory: TrackedDirectory) -> None:
    """Remove only the plain directory object recorded by the caller."""

    _before_identity_cleanup(directory)
    if not has_identity(directory.path, directory.identity):
        raise IdentityMismatchError(
            f"cleanup path identity changed; preserved for recovery: {directory.path}"
        )
    parent_chain = capture_parent_chain(directory.path.parent, directory.path)
    parent_fd: int | None = None
    windows_locks: list[int] = []
    directory_fd: int | None = None
    try:
        if os.name == "nt":
            windows_locks.extend(_lock_windows_chain(parent_chain))
            directory_fd = _open_windows_path(
                directory.path,
                directory.identity,
                directory=True,
                delete=True,
            )
            _windows_delete_bound_tree(directory.path, directory_fd)
        elif (
            os.stat in os.supports_dir_fd
            and os.unlink in os.supports_dir_fd
            and os.rmdir in os.supports_dir_fd
        ):
            import shutil

            if not shutil.rmtree.avoids_symlink_attacks:
                raise IdentityMismatchError(
                    "safe descriptor-bound recursive cleanup is unavailable; "
                    f"preserved for recovery: {directory.path}"
                )
            parent_fd = _open_verified_parent(parent_chain[-1])
            if status_identity(
                os.stat(
                    directory.path.name,
                    dir_fd=parent_fd,
                    follow_symlinks=False,
                )
            ) != directory.identity:
                raise IdentityMismatchError(
                    f"cleanup path identity changed; preserved for recovery: {directory.path}"
                )
            shutil.rmtree(directory.path.name, dir_fd=parent_fd)
        else:
            raise IdentityMismatchError(
                "safe descriptor-bound recursive cleanup is unavailable; "
                f"preserved for recovery: {directory.path}"
            )
    finally:
        if directory_fd is not None:
            os.close(directory_fd)
        if parent_fd is not None:
            os.close(parent_fd)
        for descriptor in reversed(windows_locks):
            os.close(descriptor)
