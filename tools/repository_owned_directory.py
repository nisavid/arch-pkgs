#!/usr/bin/env python3
"""Remove a repository transaction directory only through its verified inode."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import PurePath


DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW


class OwnershipError(RuntimeError):
    """The requested directory no longer names the expected owned inode."""


def parse_identity(value: str) -> tuple[int, int]:
    device, separator, inode = value.partition(":")
    if not separator or not device.isdecimal() or not inode.isdecimal():
        raise OwnershipError("expected identity must be DEV:INO")
    return int(device), int(inode)


def identity(metadata: os.stat_result) -> tuple[int, int]:
    return metadata.st_dev, metadata.st_ino


def open_absolute_directory(path: str) -> int:
    pure_path = PurePath(path)
    if not pure_path.is_absolute():
        raise OwnershipError("directory path must be absolute")
    descriptor = os.open("/", DIRECTORY_FLAGS)
    try:
        for component in pure_path.parts[1:]:
            if component in ("", ".", ".."):
                raise OwnershipError("directory path is not normalized")
            next_descriptor = os.open(component, DIRECTORY_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def open_owned_directory(path: str, expected: tuple[int, int]) -> tuple[int, int, str]:
    normalized = os.path.normpath(path)
    if normalized != path or path == "/":
        raise OwnershipError("owned directory path must be normalized and non-root")
    parent_path, name = os.path.split(path)
    if not parent_path or name in ("", ".", ".."):
        raise OwnershipError("owned directory path is unsafe")
    parent_descriptor = open_absolute_directory(parent_path)
    try:
        owned_descriptor = os.open(name, DIRECTORY_FLAGS, dir_fd=parent_descriptor)
        metadata = os.fstat(owned_descriptor)
        if not stat.S_ISDIR(metadata.st_mode) or identity(metadata) != expected:
            os.close(owned_descriptor)
            raise OwnershipError("owned directory identity changed")
        return parent_descriptor, owned_descriptor, name
    except BaseException:
        os.close(parent_descriptor)
        raise


def require_named_identity(
    parent_descriptor: int, name: str, expected: tuple[int, int]
) -> None:
    metadata = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    if not stat.S_ISDIR(metadata.st_mode) or identity(metadata) != expected:
        raise OwnershipError("owned directory name no longer identifies the opened inode")


def delete_contents(descriptor: int) -> None:
    for name in os.listdir(descriptor):
        metadata = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        if stat.S_ISDIR(metadata.st_mode):
            child_descriptor = os.open(name, DIRECTORY_FLAGS, dir_fd=descriptor)
            try:
                child_identity = identity(os.fstat(child_descriptor))
                if child_identity != identity(metadata):
                    raise OwnershipError("child directory identity changed while opening")
                delete_contents(child_descriptor)
                require_named_identity(descriptor, name, child_identity)
                os.rmdir(name, dir_fd=descriptor)
            finally:
                os.close(child_descriptor)
        else:
            os.unlink(name, dir_fd=descriptor)


def remove_owned(path: str, expected: tuple[int, int], recursive: bool) -> None:
    parent_descriptor, owned_descriptor, name = open_owned_directory(path, expected)
    try:
        if recursive:
            delete_contents(owned_descriptor)
        elif os.listdir(owned_descriptor):
            raise OwnershipError("owned directory is not empty")
        require_named_identity(parent_descriptor, name, expected)
        os.rmdir(name, dir_fd=parent_descriptor)
    finally:
        os.close(owned_descriptor)
        os.close(parent_descriptor)


def main(argv: list[str]) -> int:
    if len(argv) != 4 or argv[1] not in ("delete-tree", "remove-empty"):
        print(
            "usage: repository_owned_directory.py "
            "{delete-tree|remove-empty} ABSOLUTE_PATH DEV:INO",
            file=sys.stderr,
        )
        return 2
    try:
        remove_owned(argv[2], parse_identity(argv[3]), argv[1] == "delete-tree")
    except (OSError, OwnershipError) as error:
        print(f"repository owned-directory operation refused: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
