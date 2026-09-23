"""Colorimétrie : sRGB → CIE Lab (D65) et ΔE76, en numpy."""

import numpy as np

_SRGB_TO_XYZ = np.array(
    [
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ]
)
_WHITE_D65 = np.array([0.95047, 1.0, 1.08883])


def hex_to_rgb(code: str) -> np.ndarray:
    code = code.lstrip("#")
    return np.array([int(code[i : i + 2], 16) for i in (0, 2, 4)], dtype=np.float64) / 255.0


def srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """rgb : (..., 3) dans [0, 1] (sRGB encodé) → Lab (..., 3)."""
    rgb = np.asarray(rgb, dtype=np.float64)
    linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    xyz = linear @ _SRGB_TO_XYZ.T / _WHITE_D65
    delta = 6 / 29
    f = np.where(xyz > delta**3, np.cbrt(xyz), xyz / (3 * delta**2) + 4 / 29)
    return np.stack(
        [116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])],
        axis=-1,
    )


def palette_lab(palette: dict[str, str]) -> tuple[list[str], np.ndarray]:
    names = list(palette)
    return names, srgb_to_lab(np.array([hex_to_rgb(palette[name]) for name in names]))


def nearest_delta_e(lab: np.ndarray, reference: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Pour chaque couleur de `lab` (N, 3) : (ΔE76 à la plus proche de `reference`, indice)."""
    distances = np.linalg.norm(lab[:, None, :] - reference[None, :, :], axis=-1)
    return distances.min(axis=1), distances.argmin(axis=1)
