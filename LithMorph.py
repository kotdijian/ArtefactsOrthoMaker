from __future__ import annotations

import argparse
from pathlib import Path

from lithmorph.analysis import analyze_mesh
from lithmorph.sampling import SamplingPreset


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="LithMorph",
        description=(
            "Surface-based planform and serial-section morphometrics "
            "for normalized lithic PLY models."
        ),
    )
    parser.add_argument("ply", type=Path, help="Normalized *_rev.ply")
    parser.add_argument(
        "--preset",
        choices=[p.value for p in SamplingPreset],
        default=SamplingPreset.DEFAULT.value,
        help="Sampling density preset (default: Default=49 base sections)",
    )
    parser.add_argument(
        "--unit",
        choices=["auto", "mm", "cm", "m"],
        default="auto",
        help="Coordinate unit. auto reads sibling transform.json.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory (default: <PLY folder>/lithic_surface_analysis)",
    )
    parser.add_argument(
        "--resample-points",
        type=int,
        default=256,
        help="Points per contour component (default: 256)",
    )
    args = parser.parse_args()

    context = analyze_mesh(
        args.ply,
        out_dir=args.out,
        preset=args.preset,
        input_unit=args.unit,
        resample_points=args.resample_points,
    )

    p = context.planform
    u = context.unit_to_mm
    s = context.sampling_plan
    print("LithMorph analysis completed")
    print(f"  source: {context.source_path}")
    print(f"  shape class: {s.shape_class}")
    print(f"  sections: XZ={s.xz_count}, YZ={s.yz_count}")
    print(f"  planform area: {p.area_native2 * u * u:.3f} mm^2")
    print(f"  max width: {p.max_width_native * u:.3f} mm")
    print(
        "  max-width position: "
        f"{p.max_width_position_normalized * 100.0:.2f}% "
        "(Ymin -> Ymax)"
    )
    print(
        "  elapsed: "
        f"{context.timings.get('total', 0.0):.3f} s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
