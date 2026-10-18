"""Authorized synthetic domain smoke: actual Firestore/ADK, strict shared model cap."""

import argparse
import asyncio
import ctypes
import hashlib
import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from agents.classification import ClassifierAgent
from agents.intake.clients import GoogleGenAIClient
from agents.packets import PacketPipeline, RetryPacketClient
from agents.packets.smoke import CappedClient
from agents.workflows.planning import PlanningWorkflow
from packages.common.settings import Settings
from packages.intake.repository import FirestoreRepository
from packages.intake.service import IntakeService
from packages.intake.storage import LocalFileBlobStore
from packages.packets.service import PacketService
from packages.packs.registry import PackRegistry
from packages.planning.service import PlanningService
from packages.safety import Actor

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def paused_worker(client: Any, pid: int, parent: int, state: dict[str, Any]):
    if sys.platform != "win32":
        raise RuntimeError("worker pause smoke requires Windows")

    def running():
        return list(
            client.collection("jobs")
            .where(filter=FieldFilter("state", "==", "running"))
            .limit(1)
            .stream()
        )

    if running():
        raise ValueError("running_jobs_prevent_pause")
    command = (
        f"Get-CimInstance Win32_Process -Filter 'ProcessId={pid}' | "
        "Select-Object ProcessId,ParentProcessId,CommandLine | ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        check=True,
    )
    process = json.loads(result.stdout)
    if (
        process["ProcessId"] != pid
        or process["ParentProcessId"] != parent
        or "-m services.worker.main" not in process["CommandLine"]
    ):
        raise ValueError("worker_identity_mismatch")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtSuspendProcess.argtypes = [ctypes.c_void_p]
    ntdll.NtResumeProcess.argtypes = [ctypes.c_void_p]
    state["identityValidated"] = True
    state["noRunningJobsBeforePause"] = True
    handle = kernel.OpenProcess(0x0800, False, pid)
    if not handle:
        raise OSError("worker_handle_unavailable")
    suspended = False
    try:
        if ntdll.NtSuspendProcess(handle) != 0:
            raise OSError("worker_suspend_failed")
        suspended = True
        state["suspended"] = True
        if running():
            raise ValueError("running_job_raced_pause")
        yield
    finally:
        try:
            if suspended:
                status = ntdll.NtResumeProcess(handle)
                state["resumed"] = status == 0
                if status != 0:
                    raise OSError("worker_resume_failed")
        finally:
            kernel.CloseHandle(handle)


class ProfileRouter:
    def __init__(self, base: GoogleGenAIClient):
        self.base, self.packets = base, base.for_packets()
        self.model_id = base.model_id
        self.mode = base.mode

    async def generate(self, **kwargs: Any) -> str:
        target = (
            self.packets
            if kwargs["schema"].__name__ in {"WriterOutput", "EntailmentOutput"}
            else self.base
        )
        return await target.generate(**kwargs)


class NoDelivery:
    async def deliver(self, *args: Any) -> None:
        raise AssertionError("this measurement cannot deliver to any institution")


async def measure(args: argparse.Namespace, client: Any, report: dict[str, Any]) -> None:
    now = datetime.now(UTC)
    facts = {
        "country": {
            "value": "IN",
            "provenance": {"source": "selected", "reference": "synthetic-smoke-selection"},
        },
        "payment": {
            "method": "upi",
            "amount": {"value": "45000", "currency": "INR"},
            "timestamp": (now - timedelta(minutes=20)).isoformat(),
            "authorizedByVictim": True,
            "recipientIdentifier": {"type": "upi", "value": "safe.verify@fakebank"},
            "transactionRef": "TEST0000000001",
        },
        "contact": {"channel": "phone", "claimedIdentity": "Test Bank"},
        "victimBank": "Test Bank",
        "ongoingContact": False,
    }
    input_data = {
        "synthetic": True,
        "facts": facts,
        "mode": "canonical-facts-entry-no-intake-model",
        "generatedAt": now.isoformat(),
    }
    input_raw = json.dumps(input_data, ensure_ascii=False, sort_keys=True).encode()
    args.output.with_suffix(".input.json").write_bytes(input_raw)
    base = GoogleGenAIClient(
        Settings(
            genai_mode="live",
            intake_enabled=True,
            gcp_project_id="demo-relay-local",
            genai_project_id=args.project,
            genai_location="global",
            model_reasoning=args.model,
            packet_thinking_level="LOW",
            max_model_concurrency=1,
        )
    )
    cap = CappedClient(
        ProfileRouter(base),
        usage_source=base,
        ledger_path=args.output.with_suffix(".attempts.jsonl"),
        synthetic_input_hash=hashlib.sha256(input_raw).hexdigest(),
    )
    repo = FirestoreRepository(client)
    storage = LocalFileBlobStore(
        ROOT / ".local/primary-smoke-blobs", "http://127.0.0.1:8000", os.urandom(32)
    )
    intake = IntakeService(repo, storage, None, None)
    intake.planning = PlanningService(
        intake,
        PlanningWorkflow(
            ClassifierAgent(cap, schema_retries=0),
            PackRegistry(ROOT / "packs"),
            environment="local",
            demo_mode=True,
            allow_draft_preview=True,
        ),
    )
    packets = PacketService(
        intake,
        PacketPipeline(RetryPacketClient(cap, on_retry=cap.record_retry), timeout=35),
        NoDelivery(),
    )
    intake.packets = packets
    actor = Actor("synthetic-primary-" + uuid4().hex, "victim")
    case_id = None
    started = time.monotonic()
    report.update(
        inputSha256=hashlib.sha256(input_raw).hexdigest(),
        attemptCap=18,
        project=args.project,
        model=args.model,
        processingLocation="global",
        intakeModelUsed=False,
        classifierMode="actual-live-ADK",
        repository="actual-Firestore-emulator",
        packetRuns=[],
    )

    def snapshot(job_id):
        case = repo.get(f"cases/{case_id}")
        if case is None:
            raise ValueError("synthetic_case_missing")
        entries = [repo.get(f"cases/{case_id}/packets/{p}") for p in case.get("packetIds", [])]
        return {
            "job": repo.get(f"jobs/{job_id}"),
            "packets": entries,
            "caseStatus": case["status"],
            "providerAttempts": cap.attempts,
            "elapsedSeconds": time.monotonic() - started,
        }

    try:
        case_id = intake.create_case(
            actor, {"language": "en", "consentVersion": "1.0"}, str(uuid4())
        )["caseId"]
        report.update(caseId=case_id, actorUid=actor.uid)
        intake.update_facts(actor, case_id, {"facts": facts})
        planning_job = intake.planning.enqueue(actor, case_id, {"previewDraft": True})
        await intake.planning.process_case(planning_job["jobId"])
        report["planning"] = snapshot(planning_job["jobId"])
        if report["planning"]["job"]["state"] != "succeeded":
            report["stopped"] = "planning_failed_no_fixture_fallback"
            return
        if not (repo.get(f"cases/{case_id}") or {}).get("plan"):
            report["stopped"] = "classification_clarification_no_plan"
            return
        plan = intake.planning.get_plan(actor, case_id)
        report["plan"] = plan
        initial = packets.generate(actor, case_id, {"planId": plan["planId"]}, str(uuid4()))
        await packets.process(initial["jobId"])
        report["packetRuns"].append({"kind": "initial", **snapshot(initial["jobId"])})
        # At most one explicit resume, sharing the SAME cap and current durable packets.
        if report["packetRuns"][-1]["job"]["state"] == "failed" and cap.attempts < 18:
            resume = packets.generate(actor, case_id, {"planId": plan["planId"]}, str(uuid4()))
            await packets.process(resume["jobId"])
            report["packetRuns"].append({"kind": "explicit-resume", **snapshot(resume["jobId"])})
    finally:
        # Never leave this measurement's queued work for the normal worker to run outside its cap.
        if case_id is not None:
            for snap in (
                client.collection("jobs")
                .where(filter=FieldFilter("caseId", "==", case_id))
                .stream()
            ):

                def stop(tx, path=f"jobs/{snap.id}"):
                    job = tx.get(path)
                    if (
                        job
                        and job.get("uid") == actor.uid
                        and job.get("state") in {"queued", "running"}
                    ):
                        job.update(
                            state="failed",
                            leaseUntil=None,
                            error={"code": "smoke_stopped", "retryable": False},
                        )
                        tx.set(path, job)

                repo.atomic(stop)
        report.update(
            providerAttempts=cap.attempts,
            providerFailures=cap.failures,
            attemptLedger=cap.ledger,
            usage=base.usage_records,
            sdkFailures=base.failure_records,
            totalSeconds=time.monotonic() - started,
            institutionContact=False,
            cost=None,
        )
        await base.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--worker-pid", type=int, required=True)
    parser.add_argument("--worker-parent", type=int, required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.live or os.environ.get("FIRESTORE_EMULATOR_HOST") != "127.0.0.1:8095":
        parser.error("explicit authorized live mode and exact emulator required")
    if args.output.exists() or args.output.with_suffix(".attempts.jsonl").exists():
        parser.error("unique report/ledger required")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    client = firestore.Client(project="demo-relay-local", credentials=AnonymousCredentials())
    report = {
        "synthetic": True,
        "runAt": datetime.now(UTC).isoformat(),
        "nCases": 1,
        "fixtureFallback": False,
    }
    worker_state: dict[str, Any] = {"suspended": False, "resumed": False}
    try:
        with paused_worker(client, args.worker_pid, args.worker_parent, worker_state):
            asyncio.run(measure(args, client, report))
    except Exception as error:
        report["harnessErrorType"] = type(error).__name__
    finally:
        report["workerRestoration"] = worker_state
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
        client.close()
    print(
        json.dumps(
            {
                "report": str(args.output),
                "providerAttempts": report.get("providerAttempts", 0),
                "stopped": report.get("stopped"),
                "harnessErrorType": report.get("harnessErrorType"),
            }
        )
    )


if __name__ == "__main__":
    main()
