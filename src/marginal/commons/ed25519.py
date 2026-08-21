"""Strict dependency-free Ed25519 signature verification.

This verifier implements the RFC 8032 verification equation with canonical encodings and
prime-order subgroup checks. It intentionally does not implement permissive ZIP-215 semantics.
"""

from __future__ import annotations

import hashlib

_P = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493
_D = (-121665 * pow(121666, _P - 2, _P)) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)
_IDENTITY = (0, 1, 1, 0)
_Point = tuple[int, int, int, int]


def _point_add(left: _Point, right: _Point) -> _Point:
    x1, y1, z1, t1 = left
    x2, y2, z2, t2 = right
    a = ((y1 - x1) * (y2 - x2)) % _P
    b = ((y1 + x1) * (y2 + x2)) % _P
    c = (2 * _D * t1 * t2) % _P
    d = (2 * z1 * z2) % _P
    e = (b - a) % _P
    f = (d - c) % _P
    g = (d + c) % _P
    h = (b + a) % _P
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _scalar_multiply(point: _Point, scalar: int) -> _Point:
    result = _IDENTITY
    addend = point
    while scalar:
        if scalar & 1:
            result = _point_add(result, addend)
        addend = _point_add(addend, addend)
        scalar >>= 1
    return result


def _points_equal(left: _Point, right: _Point) -> bool:
    return (left[0] * right[2] - right[0] * left[2]) % _P == 0 and (
        left[1] * right[2] - right[1] * left[2]
    ) % _P == 0


def _decode_point(encoded: bytes) -> _Point | None:
    if len(encoded) != 32:
        return None
    value = int.from_bytes(encoded, "little")
    sign = value >> 255
    y = value & ((1 << 255) - 1)
    if y >= _P:
        return None
    y_squared = y * y % _P
    denominator = (_D * y_squared + 1) % _P
    if denominator == 0:
        return None
    x_squared = (y_squared - 1) * pow(denominator, _P - 2, _P) % _P
    x = pow(x_squared, (_P + 3) // 8, _P)
    if (x * x - x_squared) % _P != 0:
        x = x * _SQRT_M1 % _P
    if (x * x - x_squared) % _P != 0:
        return None
    if x == 0 and sign:
        return None
    if x & 1 != sign:
        x = (-x) % _P
    return (x, y, 1, x * y % _P)


_decoded_base_point = _decode_point(bytes.fromhex("58" + "66" * 31))
if _decoded_base_point is None:  # pragma: no cover - fixed RFC 8032 constant
    raise RuntimeError("invalid Ed25519 base point")
_BASE_POINT: _Point = _decoded_base_point


def _strict_prime_subgroup(point: _Point) -> bool:
    return not _points_equal(_scalar_multiply(point, 8), _IDENTITY) and _points_equal(
        _scalar_multiply(point, _L), _IDENTITY
    )


def verify_ed25519(public_key: bytes, message: bytes, signature: bytes) -> bool:
    """Return whether an Ed25519 signature is strict, canonical, and valid."""

    if not isinstance(public_key, bytes) or len(public_key) != 32:
        return False
    if not isinstance(message, bytes):
        return False
    if not isinstance(signature, bytes) or len(signature) != 64:
        return False
    encoded_r = signature[:32]
    scalar_s = int.from_bytes(signature[32:], "little")
    if scalar_s >= _L:
        return False
    public_point = _decode_point(public_key)
    point_r = _decode_point(encoded_r)
    if public_point is None or point_r is None:
        return False
    if not _strict_prime_subgroup(public_point) or not _strict_prime_subgroup(point_r):
        return False
    challenge = (
        int.from_bytes(hashlib.sha512(encoded_r + public_key + message).digest(), "little") % _L
    )
    left = _scalar_multiply(_BASE_POINT, scalar_s)
    right = _point_add(point_r, _scalar_multiply(public_point, challenge))
    return _points_equal(left, right)


__all__ = ["verify_ed25519"]
