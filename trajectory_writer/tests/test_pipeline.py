from __future__ import annotations

from pathlib import Path
from io import StringIO
import json
import tempfile
import unittest
from unittest.mock import patch
import contextlib

from PIL import Image, ImageDraw

from trajectory_writer.cli import main
from trajectory_writer.config import MachineConfig
from trajectory_writer.pipeline import build_image_job, build_text_job


def find_font() -> Path | None:
    candidates = [
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/Library/Fonts/Arial Unicode.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)
        self.machine = self.base / "machine.toml"
        self.machine.write_text(
            "\n".join(
                [
                    "[workspace]",
                    "x_min = 0.0",
                    "x_max = 650.0",
                    "y_min = 0.0",
                    "y_max = 350.0",
                    "z_min = 0.0",
                    "z_max = 550.0",
                    "",
                    "[placement]",
                    "origin_x = 120.0",
                    "origin_y = 90.0",
                    "target_width = 380.0",
                    "target_height = 160.0",
                    "scale = 1.0",
                    "rotation_deg = 0.0",
                    "mirror_x = false",
                    "mirror_y = false",
                    "",
                    "[motion]",
                    "z_up = 495.0",
                    "z_down = 450.0",
                    "axis4_enabled = false",
                    "axis4_constant = 230.0",
                    "max_points = 300",
                    "sample_step = 18.0",
                    "simplify_tolerance = 2.6",
                    "tol_xy = 2.0",
                    "tol_z = 2.0",
                    "travel_lift_delta = 20.0",
                    "return_to_origin = true",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_build_text(self) -> None:
        font = find_font()
        if font is None:
            self.skipTest("missing system font")
        result = build_text_job("交通", font, self.machine, self.base / "text_job")
        data_text = result.data_path.read_text(encoding="utf-8")
        trajectory = json.loads(result.trajectory_path.read_text(encoding="utf-8"))
        self.assertTrue(result.trajectory_path.exists())
        self.assertTrue(result.data_path.exists())
        self.assertTrue(result.preview_path.exists())
        self.assertIn("TrajectorySourceZUp := 495.0;", data_text)
        self.assertIn("TrajectorySourceZDown := 450.0;", data_text)
        self.assertIn("TrajectoryTravelLiftDelta := 20.0;", data_text)
        self.assertEqual(trajectory["motion"][-1]["x"], 120.0)
        self.assertEqual(trajectory["motion"][-1]["y"], 90.0)

    def test_build_image(self) -> None:
        image_path = self.base / "glyph.png"
        image = Image.new("RGB", (200, 120), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((20, 20, 180, 100), fill="black")
        image.save(image_path)
        result = build_image_job(image_path, self.machine, self.base / "image_job")
        data_text = result.data_path.read_text(encoding="utf-8")
        trajectory = json.loads(result.trajectory_path.read_text(encoding="utf-8"))
        self.assertTrue(result.trajectory_path.exists())
        self.assertTrue(result.data_path.exists())
        self.assertTrue(result.preview_path.exists())
        self.assertIn("TrajectorySourceZUp := 495.0;", data_text)
        self.assertIn("TrajectorySourceZDown := 450.0;", data_text)
        self.assertIn("TrajectoryTravelLiftDelta := 20.0;", data_text)
        self.assertEqual(trajectory["motion"][-1]["x"], 120.0)
        self.assertEqual(trajectory["motion"][-1]["y"], 90.0)

    def test_cli_main_help(self) -> None:
        buffer = StringIO()
        with patch("sys.argv", ["trajectory-writer", "--help"]):
            with contextlib.redirect_stdout(buffer):
                with self.assertRaises(SystemExit) as context:
                    main()
        self.assertEqual(context.exception.code, 0)
        self.assertIn("build-text", buffer.getvalue())

    def test_package_main_script_help(self) -> None:
        buffer = StringIO()
        with patch("sys.argv", ["trajectory_writer/__main__.py", "--help"]):
            with contextlib.redirect_stdout(buffer):
                with self.assertRaises(SystemExit) as context:
                    with open(Path(__file__).resolve().parents[1] / "trajectory_writer" / "__main__.py", "r", encoding="utf-8") as handle:
                        code = compile(handle.read(), "trajectory_writer/__main__.py", "exec")
                    exec(code, {"__name__": "__main__"})
        self.assertEqual(context.exception.code, 0)
        self.assertIn("build-image", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
