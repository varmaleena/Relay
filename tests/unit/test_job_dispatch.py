from unittest.mock import Mock

from packages.intake.dispatch import PubSubJobPublisher, notify_jobs


def test_wakeup_contains_only_job_identifier_and_required_metadata():
    client = Mock()
    publisher = PubSubJobPublisher(client, "projects/demo-relay/topics/relay-jobs")
    publisher(
        {"jobId": "job_123", "type": "process_case", "caseId": "case_123", "secret": "excluded"}
    )
    args, kwargs = client.publish.call_args
    assert args == ("projects/demo-relay/topics/relay-jobs", b'{"jobId":"job_123"}')
    assert kwargs == dict(
        type="process_case",
        schemaVersion="1",
        caseId="case_123",
        traceId="job_123",
        idempotencyKey="job_123",
    )
    client.publish.return_value.result.assert_called_once_with(timeout=10)


def test_failed_wakeup_does_not_undo_durable_work_or_expose_payload(caplog):
    publisher = Mock(side_effect=RuntimeError("private payload"))
    notify_jobs({"jobs/job_1": {"state": "queued"}, "cases/case_1": {"state": "queued"}}, publisher)
    publisher.assert_called_once()
    assert "job.dispatch_deferred" in caplog.text
    assert "private payload" not in caplog.text


def test_source_wakeup_uses_resource_without_inventing_victim_case():
    client = Mock()
    PubSubJobPublisher(client, "projects/demo-relay/topics/relay-jobs")(
        {"jobId": "job_123", "type": "pack_ingest", "resourceId": "src_123"}
    )
    _, attributes = client.publish.call_args
    assert attributes["resourceId"] == "src_123"
    assert "caseId" not in attributes


def test_terminal_deleted_and_nested_documents_do_not_dispatch():
    publisher = Mock()
    notify_jobs(
        {"jobs/a": None, "jobs/b": {"state": "succeeded"}, "jobs/c/nested/a": {"state": "queued"}},
        publisher,
    )
    publisher.assert_not_called()
