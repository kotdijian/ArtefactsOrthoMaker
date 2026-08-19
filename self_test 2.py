"""Geometry/file-format self test for Artifact Pose Normalizer v0.1.1.

The GUI is not launched. The test checks:
1) Slice-axis recovery for deep and shallow vessel-like meshes.
2) GLB load and GLB re-export with an identity transform.
"""
from __future__ import annotations

import math
from pathlib import Path
import tempfile

import numpy as np
import trimesh

from pose_core import (
    estimate_slice_axis,
    export_normalized_mesh,
    load_mesh_asset,
    rotation_from_a_to_b,
)


def synthetic_vessel(height=120.0, radius_bottom=35.0, radius_top=55.0, radial=180, levels=80):
    z = np.linspace(0.0, height, levels)
    th = np.linspace(0.0, 2 * np.pi, radial, endpoint=False)
    zz, tt = np.meshgrid(z, th, indexing="ij")
    r = radius_bottom + (radius_top - radius_bottom) * (zz / max(height, 1e-9))
    r *= 1.0 + 0.025 * np.cos(3.0 * tt)
    x = r * np.cos(tt)
    y = r * np.sin(tt)
    vertices = np.column_stack([x.ravel(), y.ravel(), zz.ravel()])
    faces = []
    for i in range(levels - 1):
        for j in range(radial):
            a = i * radial + j
            b = i * radial + (j + 1) % radial
            c = (i + 1) * radial + j
            d = (i + 1) * radial + (j + 1) % radial
            faces.append([a, c, b])
            faces.append([b, c, d])
    return trimesh.Trimesh(vertices=vertices, faces=np.asarray(faces), process=False)


def run_axis_case(name, mesh, target_axis):
    est = estimate_slice_axis(mesh.vertices)
    dot = abs(float(np.dot(est.direction, target_axis) / np.linalg.norm(target_axis)))
    angle = math.degrees(math.acos(np.clip(dot, -1.0, 1.0)))
    print(f"{name}: angle error={angle:.3f} deg, confidence={est.confidence:.3f}, score={est.score:.4f}")
    assert angle < 12.0, f"axis error too large: {angle}"


def glb_roundtrip_case(mesh):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        src = root / "sample.glb"
        dst = root / "sample_rev.glb"
        trimesh.Scene(mesh.copy()).export(file_obj=src, file_type="glb")
        asset = load_mesh_asset(src, "mm")
        assert len(asset.mesh.vertices) > 0
        export_normalized_mesh(asset, np.eye(4), dst)
        assert dst.exists() and dst.stat().st_size > 0
        reloaded = trimesh.load(dst, process=False)
        assert reloaded is not None
        print(f"GLB roundtrip: {dst.stat().st_size:,} bytes")


def main():
    target = np.array([0.31, -0.42, 0.853])
    target /= np.linalg.norm(target)
    r = rotation_from_a_to_b(np.array([0.0, 0.0, 1.0]), target)

    deep = synthetic_vessel(height=150, radius_bottom=35, radius_top=55)
    deep.vertices = deep.vertices @ r.T + np.array([120.0, -80.0, 30.0])
    run_axis_case("deep vessel", deep, target)

    shallow = synthetic_vessel(height=25, radius_bottom=65, radius_top=80)
    shallow.vertices = shallow.vertices @ r.T + np.array([-40.0, 160.0, -20.0])
    run_axis_case("shallow vessel", shallow, target)

    glb_roundtrip_case(deep)
    print("SELF TEST PASSED")


if __name__ == "__main__":
    main()
