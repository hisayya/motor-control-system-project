# Trajectory Writer

> **A Python CLI that turns text & images into machine-ready writing trajectories** — designed for fixed-outline writing tasks on CNC / robotic writing machines.

*(Experimental / learning-oriented project — trajectory planning + G-code-style export pipeline.)*

---

## ✨ What it does

1. **Text → trajectory** — renders glyph outlines (via `fonttools`/`svgpathtools`) into ordered pen-movement paths.
2. **Image → trajectory** — vectorizes bitmap glyphs (via `vtracer`) into drawable contours.
3. **Workspace mapping** — maps vector coordinates onto a physical machine workspace (configurable origin / scale / rotation / mirror).
4. **Motion optimization** — lift/plunge sequencing, point sampling & simplification (`max_points`, `simplify_tolerance`), and travel-lift control.

---

## 🚀 Quick start

```bash
pip install -e ".[build]"

# text → trajectory → machine instructions
trajectory-writer --task text --text "Hello" --config machine.toml

# image → trajectory
build-image --image glyph.png --config machine.toml

# apply / verify machine-format output
apply-br --input out.br
check-br --input out.br
```

### Machine config (`machine.toml`)

```toml
[workspace]   # machine travel limits (mm)
x_min = 0.0 ; x_max = 650.0 ; y_max = 350.0 ; z_max = 550.0

[placement]   # how the drawing is placed on the bed
origin_x = 120.0 ; origin_y = 90.0 ; target_width = 380.0 ; target_height = 160.0
mirror_x = true

[motion]      # pen lift/plunge + path simplification
z_up = 200.0 ; z_down = 450.0 ; max_points = 300 ; sample_step = 8.0
simplify_tolerance = 1.2 ; tol_xy = 2.0 ; tol_z = 10.0
```

---

## 📂 Layout

```
trajectory_writer/
  cli.py          # CLI entry (text / image / apply / check)
  config.py       # machine.toml parsing
  pipeline.py     # glyph → path → machine trajectory pipeline
  __main__.py
tests/
  test_pipeline.py
scripts/
  build_windows_exe.ps1   # PyInstaller windows build
.github/workflows/
  build-windows-exe.yml   # CI: build windows exe
```

---

## 🛠️ Tech stack

- **Python 3.12** · `fonttools` · `svgpathtools` · `pillow` · `vtracer`
- PyInstaller (optional) for standalone Windows builds (CI: `build-windows-exe.yml`)

---

## 📄 License

MIT — free to use, modify, and reuse.
