from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib
import json
import math
import csv
import struct
from typing import Iterable, Optional

import numpy as np
import trimesh

EPS = 1e-12


@dataclass
class AxisEstimate:
    point: np.ndarray
    direction: np.ndarray
    score: float
    confidence: float
    slice_centers: np.ndarray
    diagnostics: dict


@dataclass
class PlaneEstimate:
    point: np.ndarray
    normal: np.ndarray
    residual_rms: float
    confidence: float
    support_points: np.ndarray
    diagnostics: dict


@dataclass
class MeshAsset:
    mesh: trimesh.Trimesh
    source_path: Path
    source_sha256: str
    input_unit: str
    unit_to_mm: float
    source_normals_present: bool
    normals_status: str
    appearance_kind: str  # 'texture', 'vertex_color', 'none'
    texture_image: Optional[np.ndarray]
    uv: Optional[np.ndarray]
    vertex_colors: Optional[np.ndarray]
    vertex_normals: np.ndarray
    source_scene: Optional[trimesh.Scene]
    notes: list[str]


UNIT_TO_MM = {
    "mm": 1.0,
    "cm": 10.0,
    "m": 1000.0,
}


def normalize(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    n = np.linalg.norm(v)
    if n < EPS:
        raise ValueError("Zero-length vector")
    return v / n


def _glb_has_normal_attribute(path: Path) -> bool:
    """Inspect the GLB JSON chunk and check for a primitive NORMAL attribute.

    This checks whether normals were stored in the source GLB. Geometry normals are
    validated/recomputed separately after loading.
    """
    try:
        with path.open("rb") as f:
            header = f.read(12)
            if len(header) != 12:
                return False
            magic, version, _length = struct.unpack("<4sII", header)
            if magic != b"glTF" or version != 2:
                return False
            while True:
                chunk_header = f.read(8)
                if len(chunk_header) != 8:
                    break
                chunk_len, chunk_type = struct.unpack("<II", chunk_header)
                payload = f.read(chunk_len)
                if chunk_type == 0x4E4F534A:  # JSON
                    data = json.loads(payload.decode("utf-8").rstrip(" \t\r\n\x00"))
                    for mesh in data.get("meshes", []):
                        for primitive in mesh.get("primitives", []):
                            if "NORMAL" in primitive.get("attributes", {}):
                                return True
                    return False
    except (OSError, ValueError, json.JSONDecodeError, struct.error):
        return False
    return False


def source_has_normals(path: Path) -> bool:
    suffix = path.suffix.lower()
    try:
        if suffix == ".obj":
            with path.open("r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    s = line.lstrip()
                    if s.startswith("vn "):
                        return True
            return False
        if suffix == ".ply":
            with path.open("rb") as f:
                header = f.read(1024 * 1024)
            marker = header.find(b"end_header")
            if marker >= 0:
                header = header[: marker + len(b"end_header")]
            text = header.decode("ascii", errors="ignore").lower()
            has_nx = any(k in text for k in ("property float nx", "property double nx", "property float32 nx", "property float64 nx"))
            has_ny = any(k in text for k in ("property float ny", "property double ny", "property float32 ny", "property float64 ny"))
            has_nz = any(k in text for k in ("property float nz", "property double nz", "property float32 nz", "property float64 nz"))
            return has_nx and has_ny and has_nz
        if suffix == ".glb":
            return _glb_has_normal_attribute(path)
    except OSError:
        return False
    return False


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def area_weighted_vertex_normals(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    v = np.asarray(vertices, dtype=float)
    f = np.asarray(faces, dtype=np.int64)
    tri = v[f]
    face_cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    out = np.zeros_like(v, dtype=float)
    for i in range(3):
        np.add.at(out, f[:, i], face_cross)
    n = np.linalg.norm(out, axis=1)
    good = n > EPS
    out[good] /= n[good, None]
    out[~good] = np.array([0.0, 0.0, 1.0])
    return out


def _appearance_from_mesh(mesh: trimesh.Trimesh, notes: list[str]) -> tuple[str, Optional[np.ndarray], Optional[np.ndarray], Optional[np.ndarray]]:
    visual = mesh.visual
    kind = getattr(visual, "kind", None)

    # OBJ texture: UV + image. Trimesh keeps the diffuse image in the material for common single-material OBJ files.
    if kind == "texture":
        uv = getattr(visual, "uv", None)
        material = getattr(visual, "material", None)
        image = getattr(material, "image", None) if material is not None else None
        if uv is not None and image is not None and len(uv) == len(mesh.vertices):
            try:
                rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
            except Exception:
                rgba = np.asarray(image, dtype=np.uint8)
                if rgba.ndim == 2:
                    rgba = np.repeat(rgba[..., None], 3, axis=2)
                if rgba.shape[-1] == 3:
                    alpha = np.full((*rgba.shape[:2], 1), 255, dtype=np.uint8)
                    rgba = np.concatenate([rgba, alpha], axis=2)
            return "texture", rgba, np.asarray(uv, dtype=float), None

        # Texture metadata exists but the image could not be resolved. Try baking to vertex color.
        try:
            colors = np.asarray(visual.to_color().vertex_colors, dtype=np.uint8)
            if len(colors) == len(mesh.vertices):
                notes.append("Texture image could not be used directly; appearance was baked to vertex colors.")
                return "vertex_color", None, None, colors
        except Exception:
            pass

    # PLY vertex color (and OBJ vertex color, if present).
    if kind == "vertex":
        try:
            colors = np.asarray(visual.vertex_colors, dtype=np.uint8)
            if colors.ndim == 2 and len(colors) == len(mesh.vertices) and colors.shape[1] in (3, 4):
                return "vertex_color", None, None, colors
        except Exception:
            pass

    return "none", None, None, None


def _scene_to_single_mesh(scene: trimesh.Scene, notes: list[str]) -> trimesh.Trimesh:
    # Most artifact OBJ/PLY files contain one geometry. For scenes with multiple geometries,
    # flatten transforms and concatenate. Textures are baked to vertex colors before concatenation
    # to avoid losing appearance across multiple materials in v0.1.
    parts = []
    try:
        dumped = scene.dump(concatenate=False)
        if isinstance(dumped, trimesh.Trimesh):
            parts = [dumped]
        else:
            parts = [g for g in dumped if isinstance(g, trimesh.Trimesh)]
    except Exception:
        parts = [g.copy() for g in scene.geometry.values() if isinstance(g, trimesh.Trimesh)]
        notes.append("Scene transforms could not be flattened automatically; geometry-local transforms may need checking.")

    if not parts:
        raise ValueError("No triangle mesh geometry found in the file.")
    if len(parts) == 1:
        return parts[0]

    baked = []
    any_appearance = False
    for m in parts:
        m2 = m.copy()
        kind = getattr(m2.visual, "kind", None)
        if kind == "texture":
            try:
                m2.visual = m2.visual.to_color()
                any_appearance = True
            except Exception:
                pass
        elif kind == "vertex":
            any_appearance = True
        baked.append(m2)

    notes.append(f"Multiple geometries ({len(parts)}) were concatenated. Multi-material textures are baked to vertex colors in v0.1.")
    out = trimesh.util.concatenate(baked)
    if not any_appearance:
        out.visual = trimesh.visual.ColorVisuals(mesh=out)
    return out


def load_mesh_asset(path: str | Path, input_unit: str) -> MeshAsset:
    path = Path(path).expanduser().resolve()
    if input_unit not in UNIT_TO_MM:
        raise ValueError(f"Unsupported unit: {input_unit}")
    if path.suffix.lower() not in (".obj", ".ply", ".glb"):
        raise ValueError("v0.1.2 supports OBJ, PLY and GLB only.")

    notes: list[str] = []
    normals_present = source_has_normals(path)

    # PLY is specified to use vertex colors in this app.  Some CloudCompare PLY files
    # also contain a TextureFile comment even when usable RGB vertex colors are present.
    # Tell trimesh not to resolve that optional external image; otherwise a missing JPEG
    # produces a noisy traceback and unnecessary I/O before falling back to vertex color.
    if path.suffix.lower() == ".ply":
        loaded = trimesh.load(
            path,
            process=False,
            maintain_order=True,
            skip_materials=True,
            prefer_color="vertex",
        )
    else:
        loaded = trimesh.load(path, process=False, maintain_order=True)
    source_scene: Optional[trimesh.Scene] = None
    if isinstance(loaded, trimesh.Scene):
        # Keep an untouched copy for GLB export so scene materials/textures can be preserved.
        if path.suffix.lower() == ".glb":
            source_scene = loaded.copy()
        mesh = _scene_to_single_mesh(loaded, notes)
    elif isinstance(loaded, trimesh.Trimesh):
        mesh = loaded
        if path.suffix.lower() == ".glb":
            source_scene = trimesh.Scene(mesh.copy())
    else:
        raise ValueError(f"Unsupported geometry object: {type(loaded).__name__}")

    if len(mesh.vertices) == 0 or len(mesh.faces) == 0:
        raise ValueError("Mesh has no vertices or faces.")
    if np.asarray(mesh.faces).shape[1] != 3:
        raise ValueError("Triangle mesh is required.")

    # Validate / compute normals at load time. The calculation is always performed here;
    # source_has_normals only records whether the input already stored them.
    computed = area_weighted_vertex_normals(np.asarray(mesh.vertices), np.asarray(mesh.faces))
    valid = np.isfinite(computed).all() and np.all(np.linalg.norm(computed, axis=1) > 0.5)
    if not valid:
        raise ValueError("Normals could not be calculated reliably from the mesh geometry.")
    normals_status = "source_present_validated" if normals_present else "missing_recalculated"

    appearance_kind, texture_image, uv, vertex_colors = _appearance_from_mesh(mesh, notes)

    return MeshAsset(
        mesh=mesh,
        source_path=path,
        source_sha256=sha256_file(path),
        input_unit=input_unit,
        unit_to_mm=UNIT_TO_MM[input_unit],
        source_normals_present=normals_present,
        normals_status=normals_status,
        appearance_kind=appearance_kind,
        texture_image=texture_image,
        uv=uv,
        vertex_colors=vertex_colors,
        vertex_normals=computed,
        source_scene=source_scene,
        notes=notes,
    )


def orthonormal_basis(axis: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    w = normalize(axis)
    # Choose a helper vector not parallel to w.
    helper = np.array([1.0, 0.0, 0.0]) if abs(w[0]) < 0.8 else np.array([0.0, 1.0, 0.0])
    u = normalize(np.cross(w, helper))
    v = normalize(np.cross(w, u))
    return u, v


def _fit_line_pca(points: np.ndarray, preferred_direction: Optional[np.ndarray] = None) -> tuple[np.ndarray, np.ndarray, float]:
    p = np.asarray(points, dtype=float)
    c = np.mean(p, axis=0)
    q = p - c
    cov = q.T @ q / max(len(q), 1)
    vals, vecs = np.linalg.eigh(cov)
    d = normalize(vecs[:, np.argmax(vals)])
    if preferred_direction is not None and np.dot(d, preferred_direction) < 0:
        d = -d
    residual = np.linalg.norm(np.cross(q, d), axis=1)
    rms = float(np.sqrt(np.mean(residual**2))) if len(residual) else float("inf")
    return c, d, rms


def slice_centers_along_direction(
    vertices: np.ndarray,
    direction: np.ndarray,
    n_slices: int = 36,
    trim_fraction: float = 0.04,
    min_points: int = 40,
) -> tuple[np.ndarray, dict]:
    """Estimate robust slice centers for sections perpendicular to *direction*.

    The function uses vertex bands rather than exact mesh-plane intersections. This keeps v0.1 fast
    and stable on large meshes. Each band's projected median is used as the center estimate.
    """
    verts = np.asarray(vertices, dtype=float)
    d = normalize(direction)
    u, v = orthonormal_basis(d)
    center0 = np.mean(verts, axis=0)
    rel = verts - center0
    s = rel @ d
    lo, hi = np.quantile(s, [trim_fraction, 1.0 - trim_fraction])
    if not np.isfinite(lo + hi) or hi - lo < EPS:
        raise ValueError("Degenerate extent along candidate axis.")

    edges = np.linspace(lo, hi, n_slices + 1)
    centers = []
    anisotropies = []
    radii = []
    counts = []

    for i in range(n_slices):
        mask = (s >= edges[i]) & (s < edges[i + 1])
        pts = verts[mask]
        if len(pts) < min_points:
            continue
        r = pts - center0
        x = r @ u
        y = r @ v
        # Median suppresses protrusions / handles / local damage better than mean.
        cx, cy = float(np.median(x)), float(np.median(y))
        smid = 0.5 * (edges[i] + edges[i + 1])
        centers.append(center0 + u * cx + v * cy + d * smid)

        xy = np.column_stack([x - cx, y - cy])
        cov2 = np.cov(xy, rowvar=False)
        vals = np.linalg.eigvalsh(cov2)
        vals = np.maximum(vals, EPS)
        anisotropies.append(float(abs(math.log(vals[-1] / vals[0]))))
        radii.append(float(np.median(np.linalg.norm(xy, axis=1))))
        counts.append(int(len(pts)))

    if len(centers) < 5:
        raise ValueError("Too few valid slices for center-axis estimation.")

    return np.asarray(centers), {
        "anisotropy_median": float(np.median(anisotropies)),
        "radius_median": float(np.median(radii)),
        "valid_slices": len(centers),
        "slice_counts": counts,
    }


def _end_centrality(vertices: np.ndarray, axis: np.ndarray, high_end: bool, fraction: float = 0.07) -> float:
    verts = np.asarray(vertices, dtype=float)
    d = normalize(axis)
    u, v = orthonormal_basis(d)
    c = np.mean(verts, axis=0)
    rel = verts - c
    s = rel @ d
    span = float(s.max() - s.min())
    if span < EPS:
        return 0.0
    if high_end:
        mask = s >= s.max() - span * fraction
    else:
        mask = s <= s.min() + span * fraction
    pts = rel[mask]
    if len(pts) < 20:
        return 0.0
    rr = np.sqrt((pts @ u) ** 2 + (pts @ v) ** 2)
    q10, q90 = np.quantile(rr, [0.10, 0.90])
    if q90 < EPS:
        return 0.0
    return float(q10 / q90)


def orient_axis_bottom_to_opening(vertices: np.ndarray, axis: np.ndarray) -> tuple[np.ndarray, dict]:
    """Choose the sign of an axis using an end-centrality heuristic.

    A vessel opening tends to be annular near the end (larger inner radial gap), while a base tends
    to contain geometry closer to the axis. This is a heuristic; the GUI always offers Flip Z.
    """
    d = normalize(axis)
    low = _end_centrality(vertices, d, high_end=False)
    high = _end_centrality(vertices, d, high_end=True)
    # Higher centrality => more annular => opening candidate.
    if high >= low:
        out = d
        opening = "high"
    else:
        out = -d
        opening = "low"
    confidence = min(1.0, abs(high - low) / 0.25)
    return out, {"low_end_centrality": low, "high_end_centrality": high, "sign_confidence": confidence, "opening_candidate": opening}


def estimate_slice_axis(vertices: np.ndarray, n_slices: int = 36) -> AxisEstimate:
    """Estimate the vessel center axis without assuming that height is the longest PCA axis.

    All three PCA directions are evaluated. The best candidate is the one whose perpendicular
    slices are most rotationally balanced and whose slice centers form the straightest line.
    """
    verts = np.asarray(vertices, dtype=float)
    sample = verts
    # Cap very dense meshes for axis scoring; center-axis fitting is shape-driven and does not need every vertex.
    if len(sample) > 250_000:
        idx = np.linspace(0, len(sample) - 1, 250_000, dtype=np.int64)
        sample = sample[idx]

    q = sample - np.mean(sample, axis=0)
    cov = q.T @ q / max(len(q), 1)
    vals, vecs = np.linalg.eigh(cov)
    candidates = [normalize(vecs[:, i]) for i in range(3)]

    results = []
    for cand in candidates:
        try:
            centers, diag = slice_centers_along_direction(sample, cand, n_slices=n_slices, min_points=25)
            line_p, line_d, line_rms = _fit_line_pca(centers, cand)
            radius = max(diag["radius_median"], EPS)
            straightness = line_rms / radius
            valid_penalty = max(0.0, (12 - diag["valid_slices"]) / 12.0)
            score = diag["anisotropy_median"] + 3.0 * straightness + 0.5 * valid_penalty
            results.append((score, line_p, line_d, centers, diag | {"line_rms": line_rms, "straightness": straightness}))
        except Exception:
            continue

    if not results:
        raise ValueError("Slice axis estimation failed for all PCA candidates.")
    results.sort(key=lambda x: x[0])
    best = results[0]
    second_score = results[1][0] if len(results) > 1 else best[0] * 2.0 + 1.0
    margin = max(0.0, second_score - best[0])
    confidence = float(np.clip(margin / max(second_score, EPS), 0.0, 1.0))

    signed_dir, sign_diag = orient_axis_bottom_to_opening(sample, best[2])
    # Keep the line point, only flip direction sign.
    diagnostics = best[4] | sign_diag | {
        "candidate_scores": [float(r[0]) for r in results],
        "axis_method": "pca_candidates_plus_slice_symmetry",
    }
    confidence = float(np.clip(0.65 * confidence + 0.35 * sign_diag["sign_confidence"], 0.0, 1.0))
    return AxisEstimate(best[1], signed_dir, float(best[0]), confidence, best[3], diagnostics)


def center_axis_with_fixed_vertical(vertices: np.ndarray, n_slices: int = 36) -> AxisEstimate:
    """After horizontal attitude is fixed, derive the center axis by slicing along current Z.

    The returned center axis may be slightly tilted relative to Z. That tilt is preserved and used
    for the origin intersection; it does not re-level Rim/Base/Manual modes.
    """
    centers, diag = slice_centers_along_direction(vertices, np.array([0.0, 0.0, 1.0]), n_slices=n_slices, min_points=25)
    p, d, rms = _fit_line_pca(centers, np.array([0.0, 0.0, 1.0]))
    if d[2] < 0:
        d = -d
    radius = max(diag["radius_median"], EPS)
    straightness = rms / radius
    confidence = float(np.clip(1.0 - 4.0 * straightness, 0.0, 1.0))
    return AxisEstimate(
        point=p,
        direction=d,
        score=straightness,
        confidence=confidence,
        slice_centers=centers,
        diagnostics=diag | {"line_rms": rms, "straightness": straightness, "axis_method": "fixed_vertical_slices"},
    )


def robust_plane_fit(points: np.ndarray, max_iter: int = 6, trim_sigma: float = 2.8) -> PlaneEstimate:
    pts = np.asarray(points, dtype=float)
    if len(pts) < 3:
        raise ValueError("At least three points are required to fit a plane.")
    keep = np.ones(len(pts), dtype=bool)
    normal = np.array([0.0, 0.0, 1.0])
    center = np.mean(pts, axis=0)

    for _ in range(max_iter):
        p = pts[keep]
        if len(p) < 3:
            break
        center = np.mean(p, axis=0)
        q = p - center
        cov = q.T @ q / max(len(q), 1)
        vals, vecs = np.linalg.eigh(cov)
        normal = normalize(vecs[:, np.argmin(vals)])
        residual_all = np.abs((pts - center) @ normal)
        med = float(np.median(residual_all[keep]))
        mad = float(np.median(np.abs(residual_all[keep] - med)))
        sigma = 1.4826 * mad
        threshold = max(trim_sigma * sigma, np.quantile(residual_all[keep], 0.75) * 1.25, EPS)
        new_keep = residual_all <= threshold
        if np.array_equal(new_keep, keep):
            break
        keep = new_keep

    residual = (pts[keep] - center) @ normal
    rms = float(np.sqrt(np.mean(residual**2))) if len(residual) else float("inf")
    spread = np.linalg.norm(np.ptp(pts[keep], axis=0)) if np.any(keep) else 0.0
    confidence = float(np.clip(1.0 - 8.0 * rms / max(spread, EPS), 0.0, 1.0))
    return PlaneEstimate(center, normal, rms, confidence, pts[keep], {"input_points": len(pts), "accepted_points": int(np.count_nonzero(keep))})


def _radial_extreme_points(
    vertices: np.ndarray,
    axis: np.ndarray,
    high_end: bool,
    sectors: int = 72,
    band_fraction: float = 0.10,
) -> np.ndarray:
    verts = np.asarray(vertices, dtype=float)
    d = normalize(axis)
    u, v = orthonormal_basis(d)
    c = np.mean(verts, axis=0)
    rel = verts - c
    s = rel @ d
    span = float(s.max() - s.min())
    if span < EPS:
        raise ValueError("Degenerate mesh extent.")
    if high_end:
        mask = s >= s.max() - band_fraction * span
    else:
        mask = s <= s.min() + band_fraction * span
    ids = np.where(mask)[0]
    if len(ids) < sectors:
        raise ValueError("Not enough points in end band.")
    r = rel[ids]
    x = r @ u
    y = r @ v
    theta = (np.arctan2(y, x) + 2.0 * np.pi) % (2.0 * np.pi)
    bins = np.floor(theta / (2.0 * np.pi) * sectors).astype(int)
    bins = np.clip(bins, 0, sectors - 1)
    selected = []
    for b in range(sectors):
        cand = ids[bins == b]
        if len(cand) == 0:
            continue
        vals = s[cand]
        idx = cand[np.argmax(vals) if high_end else np.argmin(vals)]
        selected.append(verts[idx])
    if len(selected) < max(12, sectors // 4):
        raise ValueError("Too few radial sectors contained valid end points.")
    return np.asarray(selected)


def estimate_rim_plane(vertices: np.ndarray, initial_axis: AxisEstimate, sectors: int = 72) -> PlaneEstimate:
    pts = _radial_extreme_points(vertices, initial_axis.direction, high_end=True, sectors=sectors, band_fraction=0.12)
    fit = robust_plane_fit(pts)
    if np.dot(fit.normal, initial_axis.direction) < 0:
        fit.normal = -fit.normal
    fit.diagnostics |= {"method": "rim_radial_extreme_robust_plane", "sectors": sectors}
    return fit


def estimate_base_plane(vertices: np.ndarray, initial_axis: AxisEstimate, sectors: int = 72) -> PlaneEstimate:
    pts = _radial_extreme_points(vertices, initial_axis.direction, high_end=False, sectors=sectors, band_fraction=0.12)
    fit = robust_plane_fit(pts)
    if np.dot(fit.normal, initial_axis.direction) < 0:
        fit.normal = -fit.normal
    fit.diagnostics |= {"method": "base_radial_support_robust_plane", "sectors": sectors}
    return fit


def plane_from_three_points(points: np.ndarray, preferred_up: Optional[np.ndarray] = None) -> PlaneEstimate:
    p = np.asarray(points, dtype=float)
    if p.shape != (3, 3):
        raise ValueError("Exactly three 3D points are required.")
    n = normalize(np.cross(p[1] - p[0], p[2] - p[0]))
    if preferred_up is not None and np.dot(n, preferred_up) < 0:
        n = -n
    return PlaneEstimate(np.mean(p, axis=0), n, 0.0, 1.0, p.copy(), {"method": "manual_three_point_plane"})


def rotation_from_a_to_b(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a = normalize(a)
    b = normalize(b)
    c = float(np.clip(np.dot(a, b), -1.0, 1.0))
    if c > 1.0 - 1e-12:
        return np.eye(3)
    if c < -1.0 + 1e-12:
        # 180 deg: pick a perpendicular axis.
        axis = orthonormal_basis(a)[0]
        # Rodrigues with theta=pi: R = -I + 2 uu^T
        return -np.eye(3) + 2.0 * np.outer(axis, axis)
    v = np.cross(a, b)
    s = np.linalg.norm(v)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]], dtype=float)
    return np.eye(3) + vx + vx @ vx * ((1.0 - c) / (s * s))


def rigid_matrix(rotation: np.ndarray | None = None, translation: np.ndarray | None = None) -> np.ndarray:
    m = np.eye(4, dtype=float)
    if rotation is not None:
        m[:3, :3] = np.asarray(rotation, dtype=float)
    if translation is not None:
        m[:3, 3] = np.asarray(translation, dtype=float)
    return m


def rotation_z_matrix(deg: float) -> np.ndarray:
    a = math.radians(float(deg))
    c, s = math.cos(a), math.sin(a)
    r = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
    return rigid_matrix(rotation=r)


def transform_points(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    p = np.asarray(points, dtype=float)
    return p @ matrix[:3, :3].T + matrix[:3, 3]


def transform_direction(direction: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    return normalize(matrix[:3, :3] @ normalize(direction))


def line_plane_z_intersection(point: np.ndarray, direction: np.ndarray, z_value: float) -> np.ndarray:
    p = np.asarray(point, dtype=float)
    d = normalize(direction)
    if abs(d[2]) < 1e-9:
        raise ValueError("Center axis is nearly parallel to the ground plane.")
    t = (float(z_value) - p[2]) / d[2]
    return p + t * d


def build_pose_transform(
    vertices_raw: np.ndarray,
    orientation_method: str,
    initial_slice_axis: AxisEstimate,
    reference_normal: Optional[np.ndarray] = None,
) -> tuple[np.ndarray, AxisEstimate, np.ndarray, dict]:
    """Build raw -> pose-normalized transform before the manual front rotation.

    - Slice: initial slice center axis itself is aligned to +Z and retained.
    - Rim/Base/Manual: reference plane normal is aligned to +Z first; then the center axis is
      re-estimated from Z slices, without re-leveling the object.
    - Origin: center-axis intersection with the post-orientation AABB lower plane z=zmin.
    """
    method = orientation_method.lower()
    if method == "slice":
        ref = initial_slice_axis.direction
    else:
        if reference_normal is None:
            raise ValueError(f"{orientation_method} requires a reference normal.")
        ref = normalize(reference_normal)

    r = rotation_from_a_to_b(ref, np.array([0.0, 0.0, 1.0]))
    m_orient = rigid_matrix(rotation=r)
    oriented = transform_points(vertices_raw, m_orient)

    if method == "slice":
        cp = transform_points(initial_slice_axis.point[None, :], m_orient)[0]
        cd = transform_direction(initial_slice_axis.direction, m_orient)
        center_axis = AxisEstimate(
            point=cp,
            direction=cd,
            score=initial_slice_axis.score,
            confidence=initial_slice_axis.confidence,
            slice_centers=transform_points(initial_slice_axis.slice_centers, m_orient),
            diagnostics=dict(initial_slice_axis.diagnostics) | {"retained_from_initial_slice": True},
        )
    else:
        center_axis = center_axis_with_fixed_vertical(oriented)

    zmin = float(oriented[:, 2].min())
    origin_oriented = line_plane_z_intersection(center_axis.point, center_axis.direction, zmin)
    m_translate = rigid_matrix(translation=-origin_oriented)
    m_pose = m_translate @ m_orient

    center_axis_after = AxisEstimate(
        point=transform_points(center_axis.point[None, :], m_translate)[0],
        direction=center_axis.direction.copy(),
        score=center_axis.score,
        confidence=center_axis.confidence,
        slice_centers=transform_points(center_axis.slice_centers, m_translate),
        diagnostics=dict(center_axis.diagnostics),
    )

    info = {
        "orientation_method": method,
        "orientation_reference_normal_raw": np.asarray(ref, float).tolist(),
        "oriented_bbox_zmin_before_translation": zmin,
        "origin_in_oriented_coordinates": origin_oriented.tolist(),
        "origin_definition": "center_axis_intersection_with_posture_AABB_lower_plane",
        "ground_plane_definition": "posture_AABB_zmin",
    }
    return m_pose, center_axis_after, origin_oriented, info


def final_transform_matrix(pose_matrix: np.ndarray, front_rotation_deg: float) -> np.ndarray:
    return rotation_z_matrix(front_rotation_deg) @ pose_matrix


def angle_between_deg(a: np.ndarray, b: np.ndarray) -> float:
    c = float(np.clip(np.dot(normalize(a), normalize(b)), -1.0, 1.0))
    return float(math.degrees(math.acos(c)))


def export_matrix_csv(path: str | Path, matrix: np.ndarray) -> None:
    path = Path(path)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for row in np.asarray(matrix, dtype=float):
            writer.writerow([f"{x:.12g}" for x in row])


def export_matrix_txt(path: str | Path, matrix: np.ndarray) -> None:
    """Write a whitespace-delimited 4x4 matrix convenient for CloudCompare -APPLY_TRANS."""
    path = Path(path)
    with path.open("w", encoding="utf-8") as f:
        for row in np.asarray(matrix, dtype=float):
            f.write(" ".join(f"{x:.12g}" for x in row) + "\n")


def _jsonify(obj):
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): _jsonify(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonify(v) for v in obj]
    return obj


def export_transform_json(path: str | Path, data: dict) -> None:
    with Path(path).open("w", encoding="utf-8") as f:
        json.dump(_jsonify(data), f, ensure_ascii=False, indent=2)


def transformed_mesh(asset: MeshAsset, matrix: np.ndarray) -> trimesh.Trimesh:
    out = asset.mesh.copy()
    out.vertices = transform_points(np.asarray(asset.mesh.vertices), matrix)
    # Force fresh normal calculation after transform.
    try:
        out._cache.clear()
        _ = out.vertex_normals
    except Exception:
        pass
    return out


def export_normalized_mesh(asset: MeshAsset, matrix: np.ndarray, output_path: str | Path) -> list[Path]:
    """Export a raw->normalized model using the source file format.

    OBJ/PLY use the analysis mesh. For GLB, when the source was a Scene, the final
    transform is applied at scene level so geometry instances/materials/textures are
    retained by the GLB exporter as far as trimesh supports them.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = output_path.suffix.lower()

    if suffix == ".glb" and asset.source_scene is not None:
        scene = asset.source_scene.copy()
        scene.apply_transform(np.asarray(matrix, dtype=float))
        scene.export(file_obj=output_path, file_type="glb")
        return [output_path]

    mesh = transformed_mesh(asset, matrix)
    written: list[Path] = []

    if suffix == ".obj":
        # Explicitly request sidecar assets so MTL / texture images are written next to the OBJ.
        try:
            text, assets = trimesh.exchange.obj.export_obj(
                mesh,
                include_normals=True,
                include_color=True,
                include_texture=True,
                return_texture=True,
                write_texture=False,
            )
            output_path.write_text(text, encoding="utf-8")
            written.append(output_path)
            for name, blob in assets.items():
                side = output_path.parent / name
                if isinstance(blob, str):
                    side.write_text(blob, encoding="utf-8")
                else:
                    side.write_bytes(blob)
                written.append(side)
            return written
        except Exception:
            mesh.export(output_path)
            return [output_path]

    mesh.export(output_path)
    return [output_path]
