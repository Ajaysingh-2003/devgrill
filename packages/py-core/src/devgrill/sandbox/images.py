"""Make sure sandbox images exist: pull pinned images, build base-app folders.

Built images carry a `devgrill.content-hash` label (a hash of their build folder), so an
edited Dockerfile or source is rebuilt on the next boot and an unchanged one never is.
Builds shell out to `docker build` (BuildKit); the Engine API's legacy builder is deprecated.
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import aiodocker
from aiodocker.exceptions import DockerError

from devgrill.sandbox.driver import SandboxError

HASH_LABEL = "devgrill.content-hash"
_SKIP = {"__pycache__", ".git", ".venv", "node_modules"}


def folder_hash(folder: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        if _SKIP.intersection(path.relative_to(folder).parts):
            continue
        digest.update(path.relative_to(folder).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
        digest.update(b"\0")
    return digest.hexdigest()[:16]


async def _image_labels(docker: aiodocker.Docker, tag: str) -> dict[str, str] | None:
    try:
        info = await docker.images.inspect(tag)
    except DockerError as exc:
        if exc.status == 404:
            return None
        raise
    return (info.get("Config") or {}).get("Labels") or {}


async def build_image(tag: str, folder: Path, *, content_hash: str | None = None) -> None:
    content_hash = content_hash or folder_hash(folder)
    proc = await asyncio.create_subprocess_exec(
        "docker",
        "build",
        "--quiet",
        "--label",
        f"{HASH_LABEL}={content_hash}",
        "-t",
        tag,
        str(folder),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise SandboxError(f"building {tag} failed:\n{err.decode(errors='replace')[-4000:]}")
    del out


async def ensure_built(docker: aiodocker.Docker, tag: str, folder: Path) -> bool:
    """Build `folder` as `tag` unless an image with the same content hash exists. True if built."""
    wanted = folder_hash(folder)
    labels = await _image_labels(docker, tag)
    if labels is not None and labels.get(HASH_LABEL) == wanted:
        return False
    await build_image(tag, folder, content_hash=wanted)
    return True


async def ensure_pulled(docker: aiodocker.Docker, image: str) -> bool:
    if await _image_labels(docker, image) is not None:
        return False
    try:
        await docker.images.pull(image)
    except DockerError as exc:
        raise SandboxError(f"pulling {image} failed: {exc.message}") from exc
    return True
