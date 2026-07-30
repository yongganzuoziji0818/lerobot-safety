#!/usr/bin/env python3
"""Authenticated, pickle-free array transport for the V3-B1 loopback IPC."""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import socket
import struct
from typing import Any

import numpy as np

SCHEMA_VERSION = 1
MAX_HEADER_BYTES = 64 * 1024
MAX_PAYLOAD_BYTES = 512 * 1024 * 1024
_LENGTH = struct.Struct("!Q")


def _canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def logical_array_sha256(arrays: dict[str, np.ndarray]) -> str:
    digest = hashlib.sha256()
    for key in sorted(arrays):
        value = np.ascontiguousarray(np.asarray(arrays[key]))
        digest.update(key.encode("utf-8"))
        digest.update(str(value.dtype).encode("ascii"))
        digest.update(_canonical_json({"shape": list(value.shape)}))
        digest.update(value.tobytes(order="C"))
    return digest.hexdigest()


def array_census(arrays: dict[str, np.ndarray]) -> dict[str, dict[str, Any]]:
    return {
        key: {"shape": list(np.asarray(value).shape), "dtype": str(np.asarray(value).dtype)}
        for key, value in sorted(arrays.items())
    }


def pack_arrays(arrays: dict[str, np.ndarray]) -> bytes:
    buffer = io.BytesIO()
    normalized = {key: np.asarray(value) for key, value in arrays.items()}
    np.savez(buffer, **normalized)
    payload = buffer.getvalue()
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise RuntimeError(f"IPC_PAYLOAD_TOO_LARGE:{len(payload)}")
    return payload


def unpack_arrays(payload: bytes) -> dict[str, np.ndarray]:
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise RuntimeError(f"IPC_PAYLOAD_TOO_LARGE:{len(payload)}")
    with np.load(io.BytesIO(payload), allow_pickle=False) as archive:
        return {key: np.array(archive[key], copy=True) for key in archive.files}


def _recv_exact(sock: socket.socket, count: int) -> bytes:
    chunks: list[bytes] = []
    remaining = count
    while remaining:
        block = sock.recv(min(1024 * 1024, remaining))
        if not block:
            raise RuntimeError("IPC_UNEXPECTED_EOF")
        chunks.append(block)
        remaining -= len(block)
    return b"".join(chunks)


def _send_frame(sock: socket.socket, payload: bytes) -> None:
    sock.sendall(_LENGTH.pack(len(payload)))
    sock.sendall(payload)


def _recv_frame(sock: socket.socket, maximum: int) -> bytes:
    (length,) = _LENGTH.unpack(_recv_exact(sock, _LENGTH.size))
    if length > maximum:
        raise RuntimeError(f"IPC_FRAME_TOO_LARGE:{length}:{maximum}")
    return _recv_exact(sock, length)


def send_message(
    sock: socket.socket,
    token: bytes,
    header: dict[str, Any],
    arrays: dict[str, np.ndarray] | None = None,
) -> dict[str, Any]:
    payload = b"" if arrays is None else pack_arrays(arrays)
    unsigned = {
        **header,
        "schema_version": SCHEMA_VERSION,
        "payload_bytes": len(payload),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
    }
    signature = hmac.new(
        token, _canonical_json(unsigned) + payload, hashlib.sha256
    ).hexdigest()
    signed = {**unsigned, "hmac_sha256": signature}
    encoded = _canonical_json(signed)
    if len(encoded) > MAX_HEADER_BYTES:
        raise RuntimeError(f"IPC_HEADER_TOO_LARGE:{len(encoded)}")
    _send_frame(sock, encoded)
    _send_frame(sock, payload)
    return signed


def receive_message(
    sock: socket.socket, token: bytes
) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    header_bytes = _recv_frame(sock, MAX_HEADER_BYTES)
    payload = _recv_frame(sock, MAX_PAYLOAD_BYTES)
    header = json.loads(header_bytes.decode("ascii"))
    signature = header.pop("hmac_sha256", None)
    if header.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeError("IPC_SCHEMA_VERSION")
    if header.get("payload_bytes") != len(payload):
        raise RuntimeError("IPC_PAYLOAD_LENGTH")
    if header.get("payload_sha256") != hashlib.sha256(payload).hexdigest():
        raise RuntimeError("IPC_PAYLOAD_SHA256")
    expected = hmac.new(
        token, _canonical_json(header) + payload, hashlib.sha256
    ).hexdigest()
    if not isinstance(signature, str) or not hmac.compare_digest(signature, expected):
        raise RuntimeError("IPC_HMAC")
    arrays = {} if not payload else unpack_arrays(payload)
    return {**header, "hmac_sha256": signature}, arrays

