from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import tomllib


@dataclass(slots=True)
class MachineConfig:
    workspace_x_min: float
    workspace_x_max: float
    workspace_y_min: float
    workspace_y_max: float
    z_min: float
    z_max: float
    origin_x: float
    origin_y: float
    target_width: float
    target_height: float
    scale: float
    rotation_deg: float
    mirror_x: bool
    mirror_y: bool
    z_up: float
    z_down: float
    axis4_enabled: bool
    axis4_constant: float
    max_points: int
    sample_step: float
    simplify_tolerance: float
    tol_xy: float
    tol_z: float
    travel_lift_delta: float
    return_to_origin: bool

    @classmethod
    def from_file(cls, path: str | Path) -> "MachineConfig":
        data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
        workspace = data.get("workspace", {})
        placement = data.get("placement", {})
        motion = data.get("motion", {})
        config = cls(
            workspace_x_min=float(workspace.get("x_min", 0.0)),
            workspace_x_max=float(workspace.get("x_max", 650.0)),
            workspace_y_min=float(workspace.get("y_min", 0.0)),
            workspace_y_max=float(workspace.get("y_max", 350.0)),
            z_min=float(workspace.get("z_min", 0.0)),
            z_max=float(workspace.get("z_max", 550.0)),
            origin_x=float(placement.get("origin_x", 120.0)),
            origin_y=float(placement.get("origin_y", 90.0)),
            target_width=float(placement.get("target_width", 380.0)),
            target_height=float(placement.get("target_height", 160.0)),
            scale=float(placement.get("scale", 1.0)),
            rotation_deg=float(placement.get("rotation_deg", 0.0)),
            mirror_x=bool(placement.get("mirror_x", False)),
            mirror_y=bool(placement.get("mirror_y", False)),
            z_up=float(motion.get("z_up", 300.0)),
            z_down=float(motion.get("z_down", 450.0)),
            axis4_enabled=bool(motion.get("axis4_enabled", False)),
            axis4_constant=float(motion.get("axis4_constant", 230.0)),
            max_points=int(motion.get("max_points", 300)),
            sample_step=float(motion.get("sample_step", 8.0)),
            simplify_tolerance=float(motion.get("simplify_tolerance", 1.2)),
            tol_xy=float(motion.get("tol_xy", 2.0)),
            tol_z=float(motion.get("tol_z", 10.0)),
            travel_lift_delta=float(motion.get("travel_lift_delta", 20.0)),
            return_to_origin=bool(motion.get("return_to_origin", True)),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.workspace_x_max <= self.workspace_x_min:
            raise ValueError("workspace x range is invalid")
        if self.workspace_y_max <= self.workspace_y_min:
            raise ValueError("workspace y range is invalid")
        if self.z_max <= self.z_min:
            raise ValueError("workspace z range is invalid")
        if self.target_width <= 0:
            raise ValueError("target_width must be positive")
        if self.target_height <= 0:
            raise ValueError("target_height must be positive")
        if self.scale <= 0:
            raise ValueError("scale must be positive")
        if self.sample_step <= 0:
            raise ValueError("sample_step must be positive")
        if self.simplify_tolerance < 0:
            raise ValueError("simplify_tolerance must be non-negative")
        if self.max_points <= 0 or self.max_points > 300:
            raise ValueError("max_points must be in 1..300")
        if self.z_up < self.z_min or self.z_up > self.z_max:
            raise ValueError("z_up is outside workspace")
        if self.z_down < self.z_min or self.z_down > self.z_max:
            raise ValueError("z_down is outside workspace")
        if self.travel_lift_delta < 0:
            raise ValueError("travel_lift_delta must be non-negative")

    def as_dict(self) -> dict:
        return asdict(self)
