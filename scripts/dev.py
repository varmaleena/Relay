"""Run the loopback web/API/worker and real Firebase emulators as one local stack."""

from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import IO

from scripts.dev_checkpoint import EmulatorCheckpoints

ROOT = Path(__file__).resolve().parents[1]


def checkpoint_environment(
    emulator_env: dict[str, str], inherited_env: dict[str, str], *, reuse_emulators: bool
) -> dict[str, str]:
    """Firebase export discovers its hub via os.tmpdir(), not the hub env var.

    Reused emulators were started outside this launcher's workspace TEMP. Keep
    their inherited locator directory for export commands only.
    """
    result = emulator_env.copy()
    if reuse_emulators:
        for key in ("TMP", "TEMP", "TMPDIR"):
            if key in inherited_env:
                result[key] = inherited_env[key]
            else:
                result.pop(key, None)
    return result


def wait_for_port(port: int, process: subprocess.Popen[bytes], timeout: int = 90) -> None:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if process.poll() is not None:
            raise RuntimeError("Local service exited; inspect .tmp/dev logs")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError(f"Local service did not start on loopback port {port}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reuse-emulators", action="store_true")
    parser.add_argument(
        "--without-worker",
        action="store_true",
        help="Pause queued inference for controlled local fixture testing",
    )
    args = parser.parse_args()
    os.chdir(ROOT)
    logs = ROOT / ".tmp/dev"
    logs.mkdir(parents=True, exist_ok=True)
    inherited_env = os.environ.copy()
    env = inherited_env.copy()
    env.update(
        {
            "PYTHONPATH": str(ROOT),
            "TMP": str(ROOT / ".tmp"),
            "TEMP": str(ROOT / ".tmp"),
            "CLOUDSDK_CONFIG": str(ROOT / ".local/gcloud"),
            "FIREBASE_EMULATORS_PATH": str(ROOT / ".tools/emulators"),
            "FIREBASE_AUTH_EMULATOR_HOST": "127.0.0.1:9099",
            "FIRESTORE_EMULATOR_HOST": "127.0.0.1:8095",
            "AUTH_MODE": "emulator",
            "ENVIRONMENT": "local",
            "GCP_PROJECT_ID": "demo-relay-local",
            "GENAI_PROJECT_ID": env.get("GENAI_PROJECT_ID", "work-511514"),
            "GOOGLE_CLOUD_PROJECT": "work-511514",
            "GENAI_MODE": "live",
            "GENAI_LOCATION": "global",
            "MODEL_REASONING": env.get("MODEL_REASONING", "gemini-3.8-flash"),
            "INTAKE_ENABLED": "true",
            "PLANNING_ENABLED": "true",
            "PACKETS_ENABLED": "true",
            "RECEIVER_ENABLED": "true",
            "PACKET_THINKING_LEVEL": "LOW",
            "ALLOW_DRAFT_PACK_PREVIEW": "true",
            "PACK_DIRECTORY": str(ROOT / "packs"),
            "INTAKE_STORAGE_MODE": "local",
            "INTAKE_DATA_DIRECTORY": str(ROOT / ".local/intake"),
            "MAX_MODEL_CONCURRENCY": "1",
            "ALLOWED_ORIGINS": "http://127.0.0.1:5173,http://localhost:5173",
            "VITE_AUTH_MODE": "emulator",
            "VITE_FIREBASE_PROJECT_ID": "demo-relay-local",
            "VITE_FIREBASE_API_KEY": "demo-emulator-key",
            "VITE_FIREBASE_APP_ID": "demo-relay-local-app",
            "VITE_FIREBASE_AUTH_DOMAIN": "demo-relay-local.firebaseapp.com",
            "VITE_FIREBASE_AUTH_EMULATOR_HOST": "127.0.0.1:9099",
            "VITE_API_BASE_URL": "http://127.0.0.1:8000",
        }
    )
    executable = ROOT / "node_modules/.bin"
    firebase = str(executable / ("firebase.cmd" if os.name == "nt" else "firebase"))
    vite = str(executable / ("vite.cmd" if os.name == "nt" else "vite"))
    processes: list[subprocess.Popen[bytes]] = []
    handles: list[IO[bytes]] = []
    emulator_process: subprocess.Popen[bytes] | None = None
    checkpoint_process: subprocess.Popen[bytes] | None = None
    checkpoint_target: Path | None = None
    checkpoints = EmulatorCheckpoints(ROOT / ".local")
    checkpoint_log = (logs / "checkpoint.log").open("ab")
    handles.append(checkpoint_log)
    checkpoint_started = 0.0
    stack_ready = False
    emulator_env = env.copy()
    for variable in (
        "CLOUDSDK_CONFIG",
        "GOOGLE_CLOUD_PROJECT",
        "FIREBASE_AUTH_EMULATOR_HOST",
        "FIRESTORE_EMULATOR_HOST",
    ):
        emulator_env.pop(variable, None)
    export_env = checkpoint_environment(
        emulator_env, inherited_env, reuse_emulators=args.reuse_emulators
    )

    def start(
        name: str, arguments: list[str], child_env: dict[str, str] | None = None
    ) -> subprocess.Popen[bytes]:
        handle = (logs / f"{name}.log").open("wb")
        handles.append(handle)
        process = subprocess.Popen(
            arguments,
            cwd=ROOT,
            env=child_env or env,
            stdout=handle,
            stderr=handle,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        processes.append(process)
        return process

    try:
        state = checkpoints.next()
        emulator_args = [
            firebase,
            "emulators:start",
            "--project=demo-relay-local",
            "--only=auth,firestore",
            f"--export-on-exit={state}",
        ]
        imported = checkpoints.current()
        if imported is not None:
            emulator_args.append(f"--import={imported}")
        if not args.reuse_emulators:
            emulators = start("emulators", emulator_args, emulator_env)
            emulator_process = emulators
            wait_for_port(9099, emulators, timeout=180)
            wait_for_port(8095, emulators, timeout=180)
        else:
            for port in (9099, 8095):
                with socket.create_connection(("127.0.0.1", port), timeout=2):
                    pass
        api = start(
            "api",
            [
                sys.executable,
                "-m",
                "uvicorn",
                "services.api.main:app",
                "--host=127.0.0.1",
                "--port=8000",
                "--no-access-log",
            ],
        )
        wait_for_port(8000, api)
        if not args.without_worker:
            start("worker", [sys.executable, "-m", "services.worker.main"])
        web = start("web", [vite, "apps/web", "--host=127.0.0.1", "--port=5173", "--strictPort"])
        wait_for_port(5173, web)
        stack_ready = True
        print("Relay M3 review: http://127.0.0.1:5173", flush=True)
        print("Local Firebase identities/cases; live Gemini. Synthetic data only.", flush=True)
        print(
            "Local emulator checkpoints run every 60 seconds; Ctrl+C exports on shutdown.",
            flush=True,
        )
        while all(process.poll() is None for process in processes):
            if checkpoint_process is not None:
                result = checkpoint_process.poll()
                if result is not None:
                    if result == 0 and checkpoint_target is not None:
                        checkpoints.commit(checkpoint_target)
                    checkpoint_process = None
                elif time.monotonic() - checkpoint_started > 45:
                    checkpoint_process.terminate()
                    checkpoint_process.wait(timeout=5)
                    checkpoint_process = None
            if checkpoint_process is None and time.monotonic() - checkpoint_started >= 60:
                checkpoint_target = checkpoints.next()
                checkpoint_started = time.monotonic()
                checkpoint_process = subprocess.Popen(
                    [
                        "node",
                        str(ROOT / "node_modules/firebase-tools/lib/bin/firebase.js"),
                        "emulators:export",
                        str(checkpoint_target),
                        "--force",
                        "--project=demo-relay-local",
                    ],
                    cwd=ROOT,
                    env=export_env,
                    stdout=checkpoint_log,
                    stderr=checkpoint_log,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
                )
            time.sleep(1)
        raise RuntimeError("A local service stopped; inspect .tmp/dev logs")
    except KeyboardInterrupt:
        pass
    finally:
        if checkpoint_process is not None:
            try:
                result = checkpoint_process.wait(timeout=45)
                if result == 0 and checkpoint_target is not None:
                    checkpoints.commit(checkpoint_target)
            except subprocess.TimeoutExpired:
                checkpoint_process.terminate()
        services = [process for process in reversed(processes) if process is not emulator_process]
        for process in services:
            if process.poll() is None:
                if os.name == "nt":
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    process.send_signal(signal.SIGINT)
        for process in services:
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.terminate()
        if stack_ready:
            # Export explicitly: Windows CTRL_BREAK is not Firebase's SIGINT handler.
            # In reuse mode the caller's emulator remains running after this export.
            state = checkpoints.next()
            with (logs / "export.log").open("wb") as export_log:
                try:
                    subprocess.run(
                        [
                            firebase,
                            "emulators:export",
                            str(state),
                            "--force",
                            "--project=demo-relay-local",
                        ],
                        cwd=ROOT,
                        env=export_env,
                        stdout=export_log,
                        stderr=export_log,
                        timeout=45,
                        check=True,
                    )
                    checkpoints.commit(state)
                except (subprocess.SubprocessError, OSError):
                    print("Emulator export failed; inspect .tmp/dev/export.log.", flush=True)
        if emulator_process is not None and emulator_process.poll() is None:
            emulator_process.send_signal(
                signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGINT
            )
            try:
                emulator_process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                emulator_process.terminate()
        for handle in handles:
            handle.close()


if __name__ == "__main__":
    main()
