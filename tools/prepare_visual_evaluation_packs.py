"""Create non-release local evaluation packs from already-verified artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import zipfile


RUNTIME_TAG = "b10516"
PROMPT_SCHEMA = "visual-understanding-v1"
MODELS = {
    "qwen2.5-vl-7b": {
        "model": "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf",
        "projector": "mmproj-Qwen2.5-VL-7B-Instruct-f16.gguf",
        "id": "Qwen/Qwen2.5-VL-7B-Instruct",
        "family": "qwen2.5-vl",
        "revision": "508edd0afaa66bb9e9f40587acc2184f02daf1f6",
        "source": "https://huggingface.co/ggml-org/Qwen2.5-VL-7B-Instruct-GGUF",
        "upstream": "https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct",
    },
    "smolvlm2-2.2b": {
        "model": "SmolVLM2-2.2B-Instruct-Q4_K_M.gguf",
        "projector": "mmproj-SmolVLM2-2.2B-Instruct-f16.gguf",
        "id": "HuggingFaceTB/SmolVLM2-2.2B-Instruct",
        "family": "smolvlm2",
        "revision": "1bc3c9f74ceafd4c8d4411cc9cf188bba3798f91",
        "source": "https://huggingface.co/ggml-org/SmolVLM2-2.2B-Instruct-GGUF",
        "upstream": "https://huggingface.co/HuggingFaceTB/SmolVLM2-2.2B-Instruct",
    },
}
BACKENDS = {
    "cpu": "llama-b10516-bin-win-cpu-x64.zip",
    "vulkan": "llama-b10516-bin-win-vulkan-x64.zip",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hardlink_or_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def create_packs(downloads: Path, root: Path) -> tuple[Path, ...]:
    downloads = downloads.resolve()
    root = root.resolve()
    if root == downloads or root.is_relative_to(downloads):
        raise ValueError("Pack root must be separate from the verified downloads directory.")
    runtime_staging = root / "_runtime-staging"
    runtime_staging.mkdir(parents=True, exist_ok=False)
    runtime_roots = {}
    for backend, archive_name in BACKENDS.items():
        archive = downloads / archive_name
        destination = runtime_staging / backend
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(destination)
        executable = next(destination.rglob("llama-server.exe"), None)
        if executable is None:
            raise ValueError(f"Runtime archive does not contain llama-server.exe: {archive_name}")
        runtime_roots[backend] = executable.parent

    manifests = []
    try:
        for model_key, model in MODELS.items():
            source_model = downloads / model["model"]
            source_projector = downloads / model["projector"]
            model_hash = sha256(source_model)
            projector_hash = sha256(source_projector)
            for backend in BACKENDS:
                pack = root / f"{model_key}-{backend}-eval"
                pack.mkdir(parents=True, exist_ok=False)
                shutil.copytree(runtime_roots[backend], pack / "runtime")
                model_path = pack / "models" / model["model"]
                projector_path = pack / "models" / model["projector"]
                hardlink_or_copy(source_model, model_path)
                hardlink_or_copy(source_projector, projector_path)
                notice = pack / "LICENSES" / "EVALUATION-NOTICE.txt"
                notice.parent.mkdir(parents=True)
                notice.write_text(
                    "NON-RELEASE EVALUATION PACK\n"
                    f"llama.cpp runtime: {RUNTIME_TAG}; MIT; https://github.com/ggml-org/llama.cpp\n"
                    f"GGUF source: {model['source']} at {model['revision']}\n"
                    f"Upstream model: {model['upstream']}; Apache-2.0\n"
                    "Redistribution eligibility has not been approved for a VideoText release.\n",
                    encoding="utf-8",
                )
                executable = pack / "runtime" / "llama-server.exe"
                manifest = {
                    "schema": "videotext.capability_pack",
                    "schema_version": "1.0",
                    "capability": "visual_understanding",
                    "pack_id": f"{model_key}-{backend}-evaluation",
                    "pack_version": "0.0.1-eval",
                    "provider_id": "local-llama-cpp",
                    "runtime": {
                        "family": "llama.cpp", "version": RUNTIME_TAG, "backend": backend,
                        "executable": "runtime/llama-server.exe",
                    },
                    "model": {
                        "id": model["id"], "family": model["family"], "revision": model["revision"],
                        "model_file": f"models/{model['model']}",
                        "projector_file": f"models/{model['projector']}",
                        "license": "Apache-2.0", "source_repository": model["source"],
                        "redistribution_provenance": "Official ggml-org GGUF; evaluation only; release redistribution unresolved.",
                    },
                    "supported_prompt_schema_revisions": [PROMPT_SCHEMA],
                    "supported_image_media_types": ["image/png"],
                    "minimum_videotext_version": "1.8.0-dev",
                    "network_required": False,
                    "files": [
                        {"path": "runtime/llama-server.exe", "sha256": sha256(executable)},
                        {"path": f"models/{model['model']}", "sha256": model_hash},
                        {"path": f"models/{model['projector']}", "sha256": projector_hash},
                        {"path": "LICENSES/EVALUATION-NOTICE.txt", "sha256": sha256(notice)},
                    ],
                    "license_notice_paths": ["LICENSES/EVALUATION-NOTICE.txt"],
                }
                manifest_path = pack / "videotext-capability-pack.json"
                manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
                manifests.append(manifest_path)
    finally:
        shutil.rmtree(runtime_staging, ignore_errors=True)
    return tuple(manifests)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--downloads", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    for manifest in create_packs(args.downloads, args.root):
        print(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
