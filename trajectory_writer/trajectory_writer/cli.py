from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import apply_br_job, build_image_job, build_text_job, check_br_job


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_text = subparsers.add_parser("build-text")
    build_text.add_argument("--text", required=True)
    build_text.add_argument("--font", required=True)
    build_text.add_argument("--machine", required=True)
    build_text.add_argument("--out", required=True)
    build_text.set_defaults(handler=run_build_text)

    build_image = subparsers.add_parser("build-image")
    build_image.add_argument("--input", required=True)
    build_image.add_argument("--machine", required=True)
    build_image.add_argument("--out", required=True)
    build_image.set_defaults(handler=run_build_image)

    apply_br = subparsers.add_parser("apply-br")
    apply_br.add_argument("--job", required=True)
    apply_br.add_argument("--hmi-project", required=True)
    apply_br.set_defaults(handler=run_apply_br)

    check_br = subparsers.add_parser("check-br")
    check_br.add_argument("--hmi-project", required=True)
    check_br.set_defaults(handler=run_check_br)

    args = parser.parse_args()
    args.handler(args)


def build_text_entry() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--font", required=True)
    parser.add_argument("--machine", required=True)
    parser.add_argument("--out", required=True)
    run_build_text(parser.parse_args())


def build_image_entry() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--machine", required=True)
    parser.add_argument("--out", required=True)
    run_build_image(parser.parse_args())


def apply_br_entry() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    parser.add_argument("--hmi-project", required=True)
    run_apply_br(parser.parse_args())


def check_br_entry() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hmi-project", required=True)
    run_check_br(parser.parse_args())


def run_build_text(args: argparse.Namespace) -> None:
    result = build_text_job(args.text, args.font, args.machine, args.out)
    print(json.dumps(to_payload(result), ensure_ascii=False, indent=2))


def run_build_image(args: argparse.Namespace) -> None:
    result = build_image_job(args.input, args.machine, args.out)
    print(json.dumps(to_payload(result), ensure_ascii=False, indent=2))


def run_apply_br(args: argparse.Namespace) -> None:
    data_path, meta_path = apply_br_job(args.job, args.hmi_project)
    print(json.dumps({"trajectory_data": str(data_path), "trajectory_meta": str(meta_path)}, ensure_ascii=False, indent=2))


def run_check_br(args: argparse.Namespace) -> None:
    print(json.dumps(check_br_job(args.hmi_project), ensure_ascii=False, indent=2))


def to_payload(result) -> dict:
    return {
        "out_dir": str(Path(result.out_dir)),
        "trajectory": str(result.trajectory_path),
        "preview": str(result.preview_path),
        "trajectory_data": str(result.data_path),
        "trajectory_meta": str(result.meta_path),
    }
