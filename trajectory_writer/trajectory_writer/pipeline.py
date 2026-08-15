from __future__ import annotations

from dataclasses import dataclass
from math import ceil, cos, hypot, radians, sin
from pathlib import Path
from tempfile import NamedTemporaryFile
import json
import re
import shutil
import xml.etree.ElementTree as ET

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTCollection, TTFont
from PIL import Image
from svgpathtools import Path as SvgPath
from svgpathtools import parse_path, svg2paths2
import vtracer

from .config import MachineConfig


Polyline = list[tuple[float, float]]


@dataclass(slots=True)
class MotionPoint:
    x: float
    y: float
    z: float
    m: float
    pen: str
    contour: int


@dataclass(slots=True)
class BuildResult:
    out_dir: Path
    trajectory_path: Path
    preview_path: Path
    data_path: Path
    meta_path: Path


def build_text_job(text: str, font_path: str | Path, machine_path: str | Path, out_dir: str | Path) -> BuildResult:
    if not text.strip():
        raise ValueError("text must not be empty")
    config = MachineConfig.from_file(machine_path)
    raw_paths = extract_text_paths(text, font_path)
    return build_job(
        raw_paths=raw_paths,
        flip_y=True,
        config=config,
        out_dir=out_dir,
        source_kind="text",
        source_value=text,
        extra={"font_path": str(font_path), "machine_path": str(machine_path)},
    )


def build_image_job(image_path: str | Path, machine_path: str | Path, out_dir: str | Path) -> BuildResult:
    config = MachineConfig.from_file(machine_path)
    raw_svg = Path(out_dir) / "raw_trace.svg"
    raw_paths = extract_image_paths(image_path, raw_svg)
    return build_job(
        raw_paths=raw_paths,
        flip_y=False,
        config=config,
        out_dir=out_dir,
        source_kind="image",
        source_value=str(image_path),
        extra={"raw_svg": str(raw_svg), "machine_path": str(machine_path)},
    )


def apply_br_job(job_dir: str | Path, hmi_project: str | Path) -> tuple[Path, Path]:
    job_path = Path(job_dir)
    project_path = Path(hmi_project)
    data_source = job_path / "TrajectoryData.st"
    meta_source = job_path / "TrajectoryMeta.json"
    if not data_source.exists():
        raise FileNotFoundError(f"missing {data_source}")
    if not meta_source.exists():
        raise FileNotFoundError(f"missing {meta_source}")
    target_dir = project_path / "Logical" / "HMIControl"
    if not target_dir.exists():
        raise FileNotFoundError(f"missing {target_dir}")
    target_data = target_dir / "TrajectoryData.st"
    target_meta = target_dir / "TrajectoryMeta.json"
    shutil.copyfile(data_source, target_data)
    shutil.copyfile(meta_source, target_meta)
    return target_data, target_meta


def check_br_job(hmi_project: str | Path) -> dict:
    project_path = Path(hmi_project)
    checks: list[dict] = []
    files = {
        "iec_program": project_path / "Logical" / "HMIControl" / "IEC.prg",
        "main": project_path / "Logical" / "HMIControl" / "Main.st",
        "variables": project_path / "Logical" / "HMIControl" / "Variables.var",
        "global": project_path / "Logical" / "Global.var",
        "trajectory_write": project_path / "Logical" / "HMIControl" / "TrajectoryWrite.st",
        "trajectory_data": project_path / "Logical" / "HMIControl" / "TrajectoryData.st",
        "auto_capture": project_path / "Logical" / "HMIControl" / "AutoPostionCapture.st",
        "auto_restore": project_path / "Logical" / "HMIControl" / "AutoPostionRestore.st",
        "datasource": project_path / "Logical" / "VCShared" / "DataSources" / "DataSource.dso",
        "page": project_path / "Logical" / "Visu" / "Pages" / "AutoMode.page",
    }
    for name, path in files.items():
        checks.append({"name": f"exists:{name}", "ok": path.exists(), "path": str(path)})
    xml_files = ["iec_program", "datasource", "page"]
    xml_roots: dict[str, ET.Element] = {}
    for name in xml_files:
        path = files[name]
        ok = False
        detail = ""
        if path.exists():
            try:
                xml_roots[name] = ET.parse(path).getroot()
                ok = True
            except Exception as exc:
                detail = str(exc)
        checks.append({"name": f"xml:{name}", "ok": ok, "detail": detail, "path": str(path)})
    text_cache = {}
    for name in ["main", "variables", "global", "trajectory_write", "trajectory_data"]:
        path = files[name]
        if path.exists():
            text_cache[name] = path.read_text(encoding="utf-8", errors="ignore")
    required_program_files = ["TrajectoryData.st", "TrajectoryWrite.st", "AutoPostionCapture.st", "AutoPostionRestore.st"]
    iec_text = files["iec_program"].read_text(encoding="utf-8", errors="ignore") if files["iec_program"].exists() else ""
    for filename in required_program_files:
        checks.append({"name": f"iec_file:{filename}", "ok": filename in iec_text})
    for token in ["TrajectoryWrite", "AutoPostionRestore", "TrajectoryData", "WorkModeLast"]:
        checks.append({"name": f"main_token:{token}", "ok": token in text_cache.get("main", "")})
    for token in ["TrajectoryLen", "TrajectoryIndex", "TrajectoryState", "TrajectoryLoaded", "TrajectoryDone", "TrajectoryFault", "TrajectoryTolXY", "TrajectoryTolZ", "TrajectorySourceZUp", "TrajectorySourceZDown", "TrajectoryUseAxis4", "TrajectoryTravelLiftDelta", "TrajectoryTravelTargetZ", "WorkModeLast"]:
        checks.append({"name": f"variables_token:{token}", "ok": token in text_cache.get("variables", "")})
    checks.append({"name": "global_token:AutoPostion", "ok": "AutoPostion" in text_cache.get("global", "")})
    for token in ["TrajectoryErrorX", "TrajectoryErrorY", "TrajectoryErrorZ", "TrajectoryTolXY", "TrajectoryTolZ", "TrajectorySourceZUp", "TrajectorySourceZDown", "TrajectoryTravelLiftDelta", "TrajectoryTravelTargetZ", "Axis03Control.Command.MoveAbsolute", "Z1", "Z2"]:
        checks.append({"name": f"trajectory_write_token:{token}", "ok": token in text_cache.get("trajectory_write", "")})
    for datapoint in ["WorkMode", "TrajectoryLen", "TrajectoryIndex", "TrajectoryState", "TrajectoryLoaded", "TrajectoryDone", "TrajectoryFault", "TrajectoryTolXY", "TrajectoryTolZ", "TrajectoryUseAxis4"]:
        checks.append({"name": f"datasource_datapoint:{datapoint}", "ok": f'Name="{datapoint}"' in files["datasource"].read_text(encoding="utf-8", errors="ignore") if files["datasource"].exists() else False})
    for token in ["DataSource.HMIControl.WorkMode", "DataSource.HMIControl.TrajectoryLen", "DataSource.HMIControl.TrajectoryIndex", "DataSource.HMIControl.TrajectoryState", "%embVirtualKey_210", "%embVirtualKey_211"]:
        checks.append({"name": f"page_token:{token}", "ok": token in files["page"].read_text(encoding="utf-8", errors="ignore") if files["page"].exists() else False})
    trajectory_len = None
    placeholder = None
    trajectory_text = text_cache.get("trajectory_data", "")
    match = re.search(r"TrajectoryLen\s*:=\s*(\d+);", trajectory_text)
    if match:
        trajectory_len = int(match.group(1))
        placeholder = trajectory_len <= 1
    checks.append({"name": "trajectory_data_len", "ok": trajectory_len is not None, "value": trajectory_len})
    checks.append({"name": "trajectory_data_not_placeholder", "ok": placeholder is False, "value": placeholder})
    failed = [check for check in checks if not check.get("ok")]
    return {
        "project": str(project_path),
        "ok": len(failed) == 0,
        "failed_count": len(failed),
        "checks": checks,
    }


def build_job(
    raw_paths: list[SvgPath],
    flip_y: bool,
    config: MachineConfig,
    out_dir: str | Path,
    source_kind: str,
    source_value: str,
    extra: dict,
) -> BuildResult:
    output_dir = Path(out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    adaptive = make_adaptive_trajectory(raw_paths, flip_y, config)
    preview_path = output_dir / "preview.svg"
    trajectory_path = output_dir / "trajectory.json"
    data_path = output_dir / "TrajectoryData.st"
    meta_path = output_dir / "TrajectoryMeta.json"
    save_preview_svg(preview_path, adaptive["contours"])
    trajectory_path.write_text(json.dumps(adaptive["trajectory"], ensure_ascii=False, indent=2), encoding="utf-8")
    data_path.write_text(render_trajectory_data(adaptive["motion"], adaptive["meta"], config), encoding="utf-8")
    meta_path.write_text(
        json.dumps(
            {
                "source_kind": source_kind,
                "source_value": source_value,
                "machine": config.as_dict(),
                **adaptive["meta"],
                **extra,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return BuildResult(
        out_dir=output_dir,
        trajectory_path=trajectory_path,
        preview_path=preview_path,
        data_path=data_path,
        meta_path=meta_path,
    )


def extract_text_paths(text: str, font_path: str | Path) -> list[SvgPath]:
    font, glyph_map = load_font_for_text(font_path, text)
    glyph_set = font.getGlyphSet()
    hmtx = font["hmtx"]
    cursor = 0.0
    paths: list[SvgPath] = []
    for char in text:
        if char.isspace():
            cursor += float(font["head"].unitsPerEm) * 0.5
            continue
        glyph_name = glyph_map.get(ord(char))
        if glyph_name is None:
            raise ValueError(f"font does not contain {char}")
        pen = SVGPathPen(glyph_set)
        glyph_set[glyph_name].draw(pen)
        commands = pen.getCommands()
        if commands:
            path = parse_path(commands).translated(cursor + 0j)
            for subpath in path.continuous_subpaths():
                if len(subpath) > 0:
                    paths.append(subpath)
        cursor += float(hmtx[glyph_name][0])
    if not paths:
        raise ValueError("no contours extracted from text")
    return paths


def load_font_for_text(font_path: str | Path, text: str) -> tuple[TTFont, dict[int, str]]:
    path = Path(font_path)
    fonts: list[TTFont]
    collection: TTCollection | None = None
    if path.suffix.lower() == ".ttc":
        collection = TTCollection(str(path))
        fonts = list(collection.fonts)
    else:
        fonts = [TTFont(str(path))]
    required = {ord(char) for char in text if not char.isspace()}
    best_font: TTFont | None = None
    best_map: dict[int, str] | None = None
    best_count = -1
    for font in fonts:
        glyph_map = font.getBestCmap() or {}
        count = sum(1 for codepoint in required if codepoint in glyph_map)
        if count > best_count:
            best_font = font
            best_map = glyph_map
            best_count = count
        if count == len(required):
            return font, glyph_map
    if best_font is None or best_map is None or best_count < len(required):
        missing = "".join(sorted({chr(codepoint) for codepoint in required if codepoint not in (best_map or {})}))
        raise ValueError(f"font does not cover text: {missing}")
    return best_font, best_map


def extract_image_paths(image_path: str | Path, raw_svg_path: str | Path) -> list[SvgPath]:
    raw_svg = Path(raw_svg_path)
    raw_svg.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(suffix=".png", delete=False) as handle:
        threshold_path = Path(handle.name)
    preprocess_image(image_path, threshold_path)
    vtracer.convert_image_to_svg_py(
        str(threshold_path),
        str(raw_svg),
        colormode="binary",
        hierarchical="stacked",
        mode="spline",
        # Keep curves faithful enough for pen plotting while letting the PLC
        # downsample adaptively later to stay within the point budget.
        filter_speckle=1,
        corner_threshold=45,
        length_threshold=4.5,
        max_iterations=16,
        splice_threshold=30,
        path_precision=8,
    )
    paths, _, _ = svg2paths2(str(raw_svg))
    threshold_path.unlink(missing_ok=True)
    extracted: list[SvgPath] = []
    for path in paths:
        for subpath in path.continuous_subpaths():
            if len(subpath) > 0:
                extracted.append(subpath)
    if not extracted:
        raise ValueError("no contours extracted from image")
    return extracted


def preprocess_image(image_path: str | Path, output_path: str | Path) -> None:
    image = Image.open(image_path).convert("L")
    binary = image.point(lambda value: 0 if value < 200 else 255)
    binary.save(output_path)


def make_adaptive_trajectory(raw_paths: list[SvgPath], flip_y: bool, config: MachineConfig) -> dict:
    sample_step = config.sample_step
    simplify_tolerance = config.simplify_tolerance
    attempts: list[tuple[float, float, int]] = []
    for _ in range(18):
        contours = [path_to_polyline(path, sample_step, flip_y) for path in raw_paths]
        contours = [contour for contour in contours if len(contour) >= 3]
        if not contours:
            raise ValueError("contours are empty after sampling")
        contours = [simplify_closed_polyline(contour, simplify_tolerance) for contour in contours]
        contours = normalize_contours(contours, config)
        contours = order_contours(contours)
        motion = contours_to_motion(contours, config)
        count = len(motion)
        attempts.append((sample_step, simplify_tolerance, count))
        if count <= config.max_points:
            return {
                "contours": contours,
                "motion": motion,
                "trajectory": to_trajectory_json(contours, motion, config, attempts),
                "meta": {
                    "point_count": count,
                    "contour_count": len(contours),
                    "sample_step": sample_step,
                    "simplify_tolerance": simplify_tolerance,
                    "bounds": contour_bounds(contours),
                    "attempts": [
                        {
                            "sample_step": round(step, 6),
                            "simplify_tolerance": round(tolerance, 6),
                            "point_count": point_count,
                        }
                        for step, tolerance, point_count in attempts
                    ],
                },
            }
        sample_step *= 1.25
        simplify_tolerance *= 1.2
    raise ValueError(f"trajectory exceeds max_points={config.max_points}: {attempts[-1][2]}")


def path_to_polyline(path: SvgPath, sample_step: float, flip_y: bool) -> Polyline:
    total_length = max(float(path.length(error=1e-4)), sample_step)
    segments = max(2, int(ceil(total_length / sample_step)))
    points: Polyline = []
    for index in range(segments + 1):
        point = path.point(index / segments)
        x = float(point.real)
        y = float(-point.imag if flip_y else point.imag)
        if not points or distance(points[-1], (x, y)) > 1e-6:
            points.append((x, y))
    if points and distance(points[0], points[-1]) > 1e-6:
        points.append(points[0])
    return points


def simplify_closed_polyline(contour: Polyline, tolerance: float) -> Polyline:
    if tolerance <= 0 or len(contour) <= 4:
        return contour
    open_points = contour[:-1]
    simplified = rdp(open_points, tolerance)
    if simplified[0] != simplified[-1]:
        simplified.append(simplified[0])
    if len(simplified) < 4:
        return contour
    return simplified


def rdp(points: Polyline, tolerance: float) -> Polyline:
    if len(points) <= 2:
        return points[:]
    max_distance = -1.0
    split_index = -1
    start = points[0]
    end = points[-1]
    for index in range(1, len(points) - 1):
        current = points[index]
        candidate = perpendicular_distance(current, start, end)
        if candidate > max_distance:
            max_distance = candidate
            split_index = index
    if max_distance <= tolerance:
        return [start, end]
    left = rdp(points[: split_index + 1], tolerance)
    right = rdp(points[split_index:], tolerance)
    return left[:-1] + right


def perpendicular_distance(point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]) -> float:
    if start == end:
        return distance(point, start)
    px, py = point
    x1, y1 = start
    x2, y2 = end
    numerator = abs((y2 - y1) * px - (x2 - x1) * py + x2 * y1 - y2 * x1)
    denominator = hypot(y2 - y1, x2 - x1)
    return numerator / denominator


def normalize_contours(contours: list[Polyline], config: MachineConfig) -> list[Polyline]:
    min_x, min_y, max_x, max_y = contour_bounds(contours)
    width = max_x - min_x
    height = max_y - min_y
    if width <= 0 or height <= 0:
        raise ValueError("contour bounds are invalid")
    target_width = config.target_width * config.scale
    target_height = config.target_height * config.scale
    factor = min(target_width / width, target_height / height)
    scaled = [
        [
            ((point[0] - min_x) * factor, (point[1] - min_y) * factor)
            for point in contour
        ]
        for contour in contours
    ]
    scaled = apply_mirror(scaled, config.mirror_x, config.mirror_y)
    scaled = apply_rotation(scaled, config.rotation_deg)
    scaled_min_x, scaled_min_y, scaled_max_x, scaled_max_y = contour_bounds(scaled)
    shifted = [
        [
            (
                round(point[0] - scaled_min_x + config.origin_x, 6),
                round(point[1] - scaled_min_y + config.origin_y, 6),
            )
            for point in contour
        ]
        for contour in scaled
    ]
    validate_workspace(shifted, config)
    return shifted


def apply_mirror(contours: list[Polyline], mirror_x: bool, mirror_y: bool) -> list[Polyline]:
    if not mirror_x and not mirror_y:
        return contours
    min_x, min_y, max_x, max_y = contour_bounds(contours)
    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0
    mirrored: list[Polyline] = []
    for contour in contours:
        mirrored.append(
            [
                (
                    center_x - (point[0] - center_x) if mirror_x else point[0],
                    center_y - (point[1] - center_y) if mirror_y else point[1],
                )
                for point in contour
            ]
        )
    return mirrored


def apply_rotation(contours: list[Polyline], rotation_deg: float) -> list[Polyline]:
    if abs(rotation_deg) < 1e-9:
        return contours
    min_x, min_y, max_x, max_y = contour_bounds(contours)
    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0
    angle = radians(rotation_deg)
    cos_angle = cos(angle)
    sin_angle = sin(angle)
    rotated: list[Polyline] = []
    for contour in contours:
        result: Polyline = []
        for x, y in contour:
            dx = x - center_x
            dy = y - center_y
            result.append(
                (
                    center_x + dx * cos_angle - dy * sin_angle,
                    center_y + dx * sin_angle + dy * cos_angle,
                )
            )
        rotated.append(result)
    return rotated


def validate_workspace(contours: list[Polyline], config: MachineConfig) -> None:
    min_x, min_y, max_x, max_y = contour_bounds(contours)
    if min_x < config.workspace_x_min or max_x > config.workspace_x_max:
        raise ValueError("x contour exceeds workspace")
    if min_y < config.workspace_y_min or max_y > config.workspace_y_max:
        raise ValueError("y contour exceeds workspace")


def order_contours(contours: list[Polyline]) -> list[Polyline]:
    remaining = [contour[:] for contour in contours]
    ordered: list[Polyline] = []
    current: tuple[float, float] | None = None
    while remaining:
        choice_index = 0
        start_index = 0
        choice_distance = float("inf")
        if current is None:
            choice_index, start_index = pick_lexicographic_start(remaining)
        else:
            for contour_index, contour in enumerate(remaining):
                core = contour[:-1]
                for point_index, point in enumerate(core):
                    candidate = distance(current, point)
                    if candidate < choice_distance - 1e-9 or (
                        abs(candidate - choice_distance) <= 1e-9 and (point[0], point[1], contour_index, point_index) < (remaining[choice_index][:-1][start_index][0], remaining[choice_index][:-1][start_index][1], choice_index, start_index)
                    ):
                        choice_index = contour_index
                        start_index = point_index
                        choice_distance = candidate
        contour = remaining.pop(choice_index)
        rotated = rotate_closed_contour(contour, start_index)
        ordered.append(rotated)
        current = rotated[0]
    return ordered


def pick_lexicographic_start(contours: list[Polyline]) -> tuple[int, int]:
    contour_index = 0
    point_index = 0
    best = contours[0][0]
    for index, contour in enumerate(contours):
        for inner_index, point in enumerate(contour[:-1]):
            if (point[0], point[1], index, inner_index) < (best[0], best[1], contour_index, point_index):
                contour_index = index
                point_index = inner_index
                best = point
    return contour_index, point_index


def rotate_closed_contour(contour: Polyline, start_index: int) -> Polyline:
    core = contour[:-1]
    rotated = core[start_index:] + core[:start_index]
    if rotated[0] != rotated[-1]:
        rotated.append(rotated[0])
    return rotated


def contours_to_motion(contours: list[Polyline], config: MachineConfig) -> list[MotionPoint]:
    motion: list[MotionPoint] = []
    axis4 = config.axis4_constant
    for contour_index, contour in enumerate(contours):
        start_x, start_y = contour[0]
        motion.append(MotionPoint(start_x, start_y, config.z_up, axis4, "up", contour_index))
        motion.append(MotionPoint(start_x, start_y, config.z_down, axis4, "down", contour_index))
        for point in contour[1:]:
            motion.append(MotionPoint(point[0], point[1], config.z_down, axis4, "down", contour_index))
        motion.append(MotionPoint(start_x, start_y, config.z_up, axis4, "up", contour_index))
    if motion and config.return_to_origin:
        motion.append(MotionPoint(config.origin_x, config.origin_y, config.z_up, axis4, "up", len(contours)))
    return motion


def contour_bounds(contours: list[Polyline]) -> tuple[float, float, float, float]:
    xs = [point[0] for contour in contours for point in contour]
    ys = [point[1] for contour in contours for point in contour]
    return min(xs), min(ys), max(xs), max(ys)


def distance(left: tuple[float, float], right: tuple[float, float]) -> float:
    return hypot(left[0] - right[0], left[1] - right[1])


def to_trajectory_json(contours: list[Polyline], motion: list[MotionPoint], config: MachineConfig, attempts: list[tuple[float, float, int]]) -> dict:
    bounds = contour_bounds(contours)
    return {
        "bounds": {
            "min_x": round(bounds[0], 6),
            "min_y": round(bounds[1], 6),
            "max_x": round(bounds[2], 6),
            "max_y": round(bounds[3], 6),
        },
        "contours": [
            [
                {"x": round(point[0], 6), "y": round(point[1], 6)}
                for point in contour
            ]
            for contour in contours
        ],
        "motion": [
            {
                "index": index,
                "x": round(point.x, 6),
                "y": round(point.y, 6),
                "z": round(point.z, 6),
                "m": round(point.m, 6),
                "pen": point.pen,
                "contour": point.contour,
            }
            for index, point in enumerate(motion)
        ],
        "machine": config.as_dict(),
        "attempts": [
            {
                "sample_step": round(sample_step, 6),
                "simplify_tolerance": round(simplify_tolerance, 6),
                "point_count": point_count,
            }
            for sample_step, simplify_tolerance, point_count in attempts
        ],
    }


def render_trajectory_data(motion: list[MotionPoint], meta: dict, config: MachineConfig) -> str:
    if not motion:
        raise ValueError("motion must not be empty")
    if len(motion) > config.max_points:
        raise ValueError("motion exceeds configured max_points")
    safe_point = MotionPoint(motion[-1].x, motion[-1].y, motion[-1].z, motion[-1].m, motion[-1].pen, motion[-1].contour)
    padded = motion + [safe_point] * (config.max_points - len(motion))
    lines = ["ACTION TrajectoryData:"]
    lines.append(f"\tTrajectoryLen := {len(motion)};")
    lines.append(f"\tTrajectoryTolXY := {format_real(config.tol_xy)};")
    lines.append(f"\tTrajectoryTolZ := {format_real(config.tol_z)};")
    lines.append(f"\tTrajectorySourceZUp := {format_real(config.z_up)};")
    lines.append(f"\tTrajectorySourceZDown := {format_real(config.z_down)};")
    lines.append(f"\tTrajectoryTravelLiftDelta := {format_real(config.travel_lift_delta)};")
    lines.append(f"\tTrajectoryUseAxis4 := {bool_literal(config.axis4_enabled)};")
    lines.append("\tTrajectoryLoaded := TRUE;")
    lines.append("\tTrajectoryDone := FALSE;")
    lines.append("\tTrajectoryFault := FALSE;")
    lines.append("\tTrajectoryIndex := 0;")
    lines.append("\tTrajectoryState := 0;")
    for index, point in enumerate(padded):
        lines.append(f"\tModPostion.X[{index}] := {format_real(point.x)};")
        lines.append(f"\tModPostion.Y[{index}] := {format_real(point.y)};")
        lines.append(f"\tModPostion.Z[{index}] := {format_real(point.z)};")
        lines.append(f"\tModPostion.M[{index}] := {format_real(point.m)};")
    lines.append("END_ACTION")
    return "\n".join(lines) + "\n"


def format_real(value: float) -> str:
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    if "." not in text:
        text += ".0"
    if text == "-0.0":
        text = "0.0"
    return text


def bool_literal(value: bool) -> str:
    return "TRUE" if value else "FALSE"


def save_preview_svg(path: str | Path, contours: list[Polyline]) -> None:
    min_x, min_y, max_x, max_y = contour_bounds(contours)
    width = max(max_x - min_x, 1.0)
    height = max(max_y - min_y, 1.0)
    view_box = f"{min_x:.3f} {min_y:.3f} {width:.3f} {height:.3f}"
    elements: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_box}" width="{width:.3f}" height="{height:.3f}">',
        '<rect width="100%" height="100%" fill="white"/>',
    ]
    for contour in contours:
        points = " ".join(f"{x:.3f},{y:.3f}" for x, y in contour)
        elements.append(f'<polyline fill="none" stroke="black" stroke-width="1" points="{points}"/>')
    elements.append("</svg>")
    Path(path).write_text("\n".join(elements) + "\n", encoding="utf-8")
