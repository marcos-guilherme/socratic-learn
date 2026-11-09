"""Conservative identity-bound filesystem mutation helpers."""

from __future__ import annotations

import ctypes
import errno
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable
from typing import Any


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
    entries: tuple["TrackedEntry", ...]


@dataclass(frozen=True)
class TrackedEntry:
    relative: str
    identity: PathIdentity
    directory: bool


class IdentityMismatchError(OSError):
    """A pathname no longer identifies the object authorized for mutation."""


class PostMutationIdentityError(IdentityMismatchError):
    """A mutation completed, but its resulting pathname identity is ambiguous."""


class AtomicNoReplaceUnsupportedError(IdentityMismatchError):
    """The platform cannot perform an atomic no-replace rename."""


POSIX_SAME_PRINCIPAL_LIMIT = (
    "on POSIX, malicious or noncooperating same-principal processes are outside "
    "the guarantee because leaf-entry rename/unlink/rmdir operations have an "
    "irreducible TOCTOU window"
)


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
    entries: list[TrackedEntry] = []

    def capture(directory: Path) -> None:
        for item in sorted(os.scandir(directory), key=lambda entry: entry.name):
            child = Path(item.path)
            child_status = child.stat(follow_symlinks=False)
            if _is_reparse_or_symlink(child_status):
                raise IdentityMismatchError(
                    f"tracked tree contains a link or reparse point: {child}"
                )
            child_is_directory = stat.S_ISDIR(child_status.st_mode)
            if not child_is_directory and not stat.S_ISREG(child_status.st_mode):
                raise IdentityMismatchError(
                    f"tracked tree contains an unsupported entry type: {child}"
                )
            entries.append(
                TrackedEntry(
                    child.relative_to(path).as_posix(),
                    status_identity(child_status),
                    child_is_directory,
                )
            )
            if child_is_directory:
                capture(child)

    capture(path)
    return TrackedDirectory(path, status_identity(status), tuple(entries))


def _is_reparse_or_symlink(status: os.stat_result) -> bool:
    attributes = getattr(status, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(status.st_mode) or bool(attributes & reparse_flag)


def _assert_under_root(path: Path, *, root: Path) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as error:
        raise IdentityMismatchError(
            f"path escapes trusted root: {path}"
        ) from error


def require_trusted_regular_file(path: Path, *, root: Path) -> PathIdentity:
    """Return the identity of one regular file beneath a verified trusted root."""

    _assert_under_root(path, root=root)
    capture_parent_chain(root, path)
    status = path.stat(follow_symlinks=False)
    if _is_reparse_or_symlink(status):
        raise IdentityMismatchError(
            f"trusted file is a link or reparse point: {path}"
        )
    if not stat.S_ISREG(status.st_mode):
        raise IdentityMismatchError(
            f"trusted path is not a regular file: {path}"
        )
    return status_identity(status)


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


def _after_bound_replace(source: Path, destination: Path) -> None:
    """Narrow race-test hook after mutation and before pathname verification."""


def _observed_identity(path: Path) -> str:
    try:
        identity = path_identity(path)
    except OSError:
        return "missing"
    return f"({identity.device}, {identity.inode})"


def _identity_locations(root: Path, identity: PathIdentity) -> tuple[Path, ...]:
    locations: list[Path] = []
    try:
        for current, directory_names, _file_names in os.walk(
            root,
            topdown=True,
            followlinks=False,
        ):
            current_path = Path(current)
            directory_names[:] = [
                name
                for name in directory_names
                if not (current_path / name).is_symlink()
            ]
            if has_identity(current_path, identity):
                locations.append(current_path)
    except OSError:
        pass
    return tuple(locations)


def _post_mutation_error(
    source: Path,
    destination: Path,
    *,
    root: Path,
    expected_source: PathIdentity,
    source_parent: ParentIdentity,
    destination_parent: ParentIdentity,
    original: BaseException,
) -> PostMutationIdentityError:
    recovery = _identity_locations(root, destination_parent.identity)
    recovery_locations = ", ".join(str(path) for path in recovery) or "not found"
    return PostMutationIdentityError(
        "post-mutation recovery required; both current locations were preserved; "
        f"source expected=({expected_source.device}, {expected_source.inode}), "
        f"source observed={_observed_identity(source)}, destination expected="
        f"({expected_source.device}, {expected_source.inode}), destination "
        f"observed={_observed_identity(destination)}; source parent original="
        f"({source_parent.identity.device}, {source_parent.identity.inode}), "
        f"source parent observed={_observed_identity(source_parent.path)}; "
        f"destination parent original=({destination_parent.identity.device}, "
        f"{destination_parent.identity.inode}), destination parent observed="
        f"{_observed_identity(destination_parent.path)}; bound destination parent "
        f"recovery locations={recovery_locations}; original failure: "
        f"{type(original).__name__}: {original}"
    )


def _load_posix_symbol(name: str) -> Any | None:
    """Load one errno-reporting function from the process C library."""

    try:
        function = getattr(ctypes.CDLL(None, use_errno=True), name)
    except (AttributeError, OSError):
        return None
    function.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    function.restype = ctypes.c_int
    return function


def _unsupported_posix_rename(
    api: str,
    flag: str,
) -> AtomicNoReplaceUnsupportedError:
    return AtomicNoReplaceUnsupportedError(
        f"{api} with {flag} is unavailable on this kernel or filesystem; "
        "source and destination were preserved; retry on a supported local "
        "filesystem or recover manually from the reported paths"
    )


def _native_posix_rename_no_replace(
    source_parent_fd: int,
    source_name: str,
    destination_parent_fd: int,
    destination_name: str,
) -> None:
    """Invoke the platform's atomic descriptor-relative no-replace rename."""

    if sys.platform.startswith("linux"):
        api = "renameat2"
        flag_name = "RENAME_NOREPLACE"
        flag = 1 << 0
        unsupported_errors = {errno.EINVAL, errno.ENOSYS}
    elif sys.platform == "darwin":
        api = "renameatx_np"
        flag_name = "RENAME_EXCL"
        flag = 0x00000004
        unsupported_errors = {errno.ENOSYS, errno.ENOTSUP}
    else:
        raise _unsupported_posix_rename(
            "descriptor-relative rename",
            "atomic no-replace",
        )

    function = _load_posix_symbol(api)
    if function is None:
        raise _unsupported_posix_rename(api, flag_name)
    result = function(
        source_parent_fd,
        os.fsencode(source_name),
        destination_parent_fd,
        os.fsencode(destination_name),
        flag,
    )
    if result == 0:
        return
    error = ctypes.get_errno()
    if error == errno.EEXIST:
        raise FileExistsError(
            error,
            os.strerror(error),
            destination_name,
        )
    if error in unsupported_errors:
        raise _unsupported_posix_rename(api, flag_name)
    raise OSError(error, os.strerror(error), destination_name)


def _posix_entry_identity(parent_fd: int, name: str) -> PathIdentity:
    return status_identity(
        os.stat(
            name,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
    )


def _open_posix_source(
    parent_fd: int,
    name: str,
    expected: PathIdentity,
) -> int:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(name, flags, dir_fd=parent_fd)
    if status_identity(os.fstat(descriptor)) != expected:
        os.close(descriptor)
        raise IdentityMismatchError(
            f"source changed while opening descriptor-bound entry: {name}"
        )
    return descriptor


def _posix_identity_bound_replace(
    source: Path,
    destination: Path,
    source_parent_fd: int,
    destination_parent_fd: int,
    identity: PathIdentity,
) -> None:
    """Move through bound parents and reconcile any final source-entry race."""

    if _posix_entry_identity(source_parent_fd, source.name) != identity:
        raise IdentityMismatchError(
            f"source identity changed before rename: {source}"
        )
    source_fd = _open_posix_source(
        source_parent_fd,
        source.name,
        identity,
    )
    try:
        if _posix_entry_identity(source_parent_fd, source.name) != identity:
            raise IdentityMismatchError(
                f"source identity changed at rename boundary: {source}"
            )
        _native_posix_rename_no_replace(
            source_parent_fd,
            source.name,
            destination_parent_fd,
            destination.name,
        )
        try:
            moved_identity = _posix_entry_identity(
                destination_parent_fd,
                destination.name,
            )
        except OSError as error:
            raise IdentityMismatchError(
                f"destination cannot be verified after rename: {destination}"
            ) from error
        source_handle_identity = status_identity(os.fstat(source_fd))
        if moved_identity == identity and source_handle_identity == identity:
            return

        try:
            observed_source = _posix_entry_identity(source_parent_fd, source.name)
            source_observed = (
                f"({observed_source.device}, {observed_source.inode})"
            )
        except OSError:
            source_observed = "missing"
        source_parent = status_identity(os.fstat(source_parent_fd))
        destination_parent = status_identity(os.fstat(destination_parent_fd))
        raise PostMutationIdentityError(
            "post-mutation recovery required; no reverse rename was attempted; "
            f"source expected=({identity.device}, {identity.inode}), "
            f"source handle=({source_handle_identity.device}, "
            f"{source_handle_identity.inode}), source observed={source_observed}; "
            f"destination observed=({moved_identity.device}, "
            f"{moved_identity.inode}); source parent=({source_parent.device}, "
            f"{source_parent.inode}); destination parent="
            f"({destination_parent.device}, {destination_parent.inode}); "
            f"preserve source location {source} and destination recovery "
            f"location {destination}"
        )
    finally:
        os.close(source_fd)


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
    expected_source_chain: tuple[ParentIdentity, ...] | None = None,
    expected_destination_chain: tuple[ParentIdentity, ...] | None = None,
) -> PathIdentity:
    """Move a verified source without replacing any destination.

    Windows uses a source-handle-bound rename. Linux and macOS use their
    descriptor-relative native no-replace rename and verify the open source
    descriptor and destination identity across the mutation boundary.
    """

    identity = path_identity(source) if expected_source is None else expected_source
    source_chain = capture_parent_chain(root, source)
    destination_chain = capture_parent_chain(root, destination)
    if expected_source_chain is not None and source_chain != expected_source_chain:
        raise IdentityMismatchError(
            f"source parent identity changed before mutation: {source.parent}"
        )
    if (
        expected_destination_chain is not None
        and destination_chain != expected_destination_chain
    ):
        raise IdentityMismatchError(
            f"destination parent identity changed before mutation: "
            f"{destination.parent}"
        )
    source_fd: int | None = None
    destination_fd: int | None = None
    windows_locks: list[int] = []
    try:
        if os.name != "nt":
            source_fd = _open_verified_parent(source_chain[-1])
            destination_fd = _open_verified_parent(destination_chain[-1])
            _before_bound_replace(source, destination)
            verify_parent_chain(root, source, source_chain)
            verify_parent_chain(root, destination, destination_chain)
            if path_identity(source) != identity:
                raise IdentityMismatchError(
                    f"source identity changed before rename: {source}"
                )
            _posix_identity_bound_replace(
                source,
                destination,
                source_fd,
                destination_fd,
                identity,
            )
            try:
                _after_bound_replace(source, destination)
                verify_parent_chain(root, destination, destination_chain)
                if path_identity(destination) != identity:
                    raise IdentityMismatchError(
                        f"destination identity changed after rename: {destination}"
                    )
            except OSError as error:
                raise _post_mutation_error(
                    source,
                    destination,
                    root=root,
                    expected_source=identity,
                    source_parent=source_chain[-1],
                    destination_parent=destination_chain[-1],
                    original=error,
                ) from error
            return identity
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
        try:
            _after_bound_replace(source, destination)
            verify_parent_chain(root, destination, destination_chain)
            if path_identity(destination) != identity:
                raise IdentityMismatchError(
                    f"destination identity changed after rename: {destination}"
                )
        except OSError as error:
            raise _post_mutation_error(
                source,
                destination,
                root=root,
                expected_source=identity,
                source_parent=source_chain[-1],
                destination_parent=destination_chain[-1],
                original=error,
            ) from error
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


def _before_tracked_entry_delete(path: Path) -> None:
    """Race-test hook immediately before an identity-checked entry deletion."""


def _tracked_entries(directory: TrackedDirectory) -> dict[str, TrackedEntry]:
    return {entry.relative: entry for entry in directory.entries}


def _verify_tracked_tree(directory: TrackedDirectory) -> None:
    if not has_identity(directory.path, directory.identity):
        raise IdentityMismatchError(
            f"cleanup root identity changed; preserved for recovery: {directory.path}"
        )
    try:
        observed = track_directory(directory.path)
    except OSError as error:
        raise IdentityMismatchError(
            f"cleanup tree could not be verified; preserved for recovery: "
            f"{directory.path}: {error}"
        ) from error
    expected_by_name = _tracked_entries(directory)
    observed_by_name = _tracked_entries(observed)
    if set(expected_by_name) != set(observed_by_name):
        unknown = sorted(set(observed_by_name) - set(expected_by_name))
        missing = sorted(set(expected_by_name) - set(observed_by_name))
        raise IdentityMismatchError(
            "cleanup tree topology changed; entire tree was preserved for "
            f"recovery: {directory.path}; unknown={unknown}; missing={missing}"
        )
    for relative, expected in expected_by_name.items():
        actual = observed_by_name[relative]
        if (
            actual.identity != expected.identity
            or actual.directory != expected.directory
        ):
            raise IdentityMismatchError(
                "cleanup child identity or type changed; entire tree was "
                f"preserved for recovery: {directory.path / relative}; "
                f"expected=({expected.identity.device}, "
                f"{expected.identity.inode}, directory={expected.directory}); "
                f"observed=({actual.identity.device}, "
                f"{actual.identity.inode}, directory={actual.directory})"
            )


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


def _windows_delete_bound_tree(
    path: Path,
    descriptor: int,
    root: Path,
    expected: dict[str, TrackedEntry],
) -> None:
    """Delete a tree through non-delete-share handles from leaf to root."""

    _before_windows_handle_delete(path)
    for entry in os.scandir(path):
        child = Path(entry.path)
        child_status = child.stat(follow_symlinks=False)
        if _is_reparse_or_symlink(child_status):
            child_is_directory = False
        else:
            child_is_directory = stat.S_ISDIR(child_status.st_mode)
        relative = child.relative_to(root).as_posix()
        recorded = expected.get(relative)
        if (
            recorded is None
            or recorded.identity != status_identity(child_status)
            or recorded.directory != child_is_directory
        ):
            raise IdentityMismatchError(
                f"cleanup entry changed; preserved for recovery: {child}"
            )
        child_descriptor = _open_windows_path(
            child,
            status_identity(child_status),
            directory=child_is_directory,
            delete=True,
        )
        try:
            if child_is_directory:
                _windows_delete_bound_tree(child, child_descriptor, root, expected)
            else:
                _before_windows_handle_delete(child)
            _windows_mark_delete(child_descriptor)
        finally:
            os.close(child_descriptor)
    _windows_mark_delete(descriptor)


def _posix_delete_bound_tree(
    directory: TrackedDirectory,
    directory_fd: int,
    relative_parent: str = "",
) -> None:
    expected = _tracked_entries(directory)
    names = sorted(os.listdir(directory_fd))
    for name in names:
        relative = f"{relative_parent}/{name}" if relative_parent else name
        recorded = expected.get(relative)
        if recorded is None:
            raise IdentityMismatchError(
                "cleanup tree topology changed; entire remaining tree was "
                f"preserved for recovery: {directory.path}; unknown={relative}"
            )
        status = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            status_identity(status) != recorded.identity
            or stat.S_ISDIR(status.st_mode) != recorded.directory
            or _is_reparse_or_symlink(status)
        ):
            raise IdentityMismatchError(
                f"cleanup entry identity changed; preserved for recovery: "
                f"{directory.path / relative}"
            )
        path = directory.path / relative
        _before_tracked_entry_delete(path)
        status = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if status_identity(status) != recorded.identity:
            raise IdentityMismatchError(
                f"cleanup entry identity changed at deletion boundary; "
                f"preserved for recovery: {path}"
            )
        if recorded.directory:
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            child_fd = os.open(name, flags, dir_fd=directory_fd)
            try:
                if status_identity(os.fstat(child_fd)) != recorded.identity:
                    raise IdentityMismatchError(
                        f"cleanup directory changed while binding: {path}"
                    )
                _posix_delete_bound_tree(directory, child_fd, relative)
            finally:
                os.close(child_fd)
            os.rmdir(name, dir_fd=directory_fd)
        else:
            os.unlink(name, dir_fd=directory_fd)


def publish_tracked_directory(
    staging: TrackedDirectory,
    destination: Path,
    *,
    root: Path,
    validate_existing: Callable[[Path], bool],
) -> Path:
    """Publish one tracked staging tree or reuse a validated existing destination."""

    _assert_under_root(staging.path, root=root)
    _assert_under_root(destination, root=root)
    _verify_tracked_tree(staging)

    source_chain = capture_parent_chain(root, staging.path)
    destination_chain = capture_parent_chain(root, destination)

    if destination.exists():
        if validate_existing(destination):
            remove_tracked_tree(staging)
            return destination
        raise IdentityMismatchError(
            f"existing destination failed validation: {destination}"
        )

    try:
        _verify_tracked_tree(staging)
        identity_bound_replace(
            staging.path,
            destination,
            root=root,
            expected_source=staging.identity,
            expected_source_chain=source_chain,
            expected_destination_chain=destination_chain,
        )
        return destination
    except PostMutationIdentityError:
        raise
    except Exception as error:
        try:
            remove_tracked_tree(staging)
        except IdentityMismatchError as cleanup_error:
            raise cleanup_error from error
        raise


def remove_tracked_tree(directory: TrackedDirectory) -> None:
    """Remove an exact operation-owned tree or preserve it on any ambiguity."""

    _before_identity_cleanup(directory)
    _verify_tracked_tree(directory)
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
            _windows_delete_bound_tree(
                directory.path,
                directory_fd,
                directory.path,
                _tracked_entries(directory),
            )
        elif (
            os.stat in os.supports_dir_fd
            and os.unlink in os.supports_dir_fd
            and os.rmdir in os.supports_dir_fd
        ):
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
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            directory_fd = os.open(
                directory.path.name,
                flags,
                dir_fd=parent_fd,
            )
            if status_identity(os.fstat(directory_fd)) != directory.identity:
                raise IdentityMismatchError(
                    f"cleanup path changed while binding; preserved: {directory.path}"
                )
            _posix_delete_bound_tree(directory, directory_fd)
            os.rmdir(directory.path.name, dir_fd=parent_fd)
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
