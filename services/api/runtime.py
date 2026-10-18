"""Explicit runtime assembly: durable repository, scoped storage, configured Google model."""

import os
from pathlib import Path
from typing import Any

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.storage import Client as StorageClient

from packages.common.settings import Settings


def local_signing_key(directory: Path) -> bytes:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "intake-signing.key"
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        value = path.read_bytes()
    else:
        value = os.urandom(32)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(value)
    if len(value) != 32:
        raise ValueError("Invalid local storage signing key")
    return value


def create_intake_runtime(config: Settings) -> tuple[Any, Any]:
    from agents.intake.clients import GoogleGenAIClient
    from agents.intake.core import EvidenceAgent, IntakeTextAgent
    from packages.intake.repository import FirestoreRepository
    from packages.intake.service import IntakeService
    from packages.intake.storage import BlobStore, GoogleBlobStore, LocalFileBlobStore

    if not config.intake_enabled or config.genai_mode != "live":
        raise ValueError("Runtime intake requires explicitly enabled live inference")
    if config.auth_mode == "emulator":
        if os.environ.get("FIRESTORE_EMULATOR_HOST") != "127.0.0.1:8095":
            raise ValueError("Explicit loopback Firestore emulator required")
        database = firestore.Client(
            project=config.gcp_project_id, credentials=AnonymousCredentials()
        )
    else:
        if os.environ.get("FIRESTORE_EMULATOR_HOST"):
            raise ValueError("Cloud runtime cannot use Firestore emulator environment")
        database = firestore.Client(project=config.gcp_project_id, database=config.firestore_db)
    publisher = None
    if config.environment != "local":
        from google.cloud.pubsub_v1 import PublisherClient

        from packages.intake.dispatch import PubSubJobPublisher

        publisher = PubSubJobPublisher(PublisherClient(), config.pubsub_topic_jobs)
    repository = FirestoreRepository(database, job_publisher=publisher)
    blobs: BlobStore
    if config.intake_storage_mode == "local":
        directory = Path(config.intake_data_directory)
        blobs = LocalFileBlobStore(
            directory / "blobs", config.api_base_url, local_signing_key(directory)
        )
    else:
        bucket = StorageClient(project=config.gcp_project_id).bucket(config.bucket_evidence)
        blobs = GoogleBlobStore(bucket, config.storage_signing_email)
    model = GoogleGenAIClient(config)
    service = IntakeService(
        repository, blobs, IntakeTextAgent(model), EvidenceAgent(model, schema_retries=0)
    )
    if config.intake_storage_mode == "gcs":
        service.export_storage = GoogleBlobStore(
            StorageClient(project=config.gcp_project_id).bucket(config.bucket_exports),
            config.storage_signing_email,
        )
    if config.planning_enabled:
        from agents.classification import ClassifierAgent
        from agents.workflows.planning import PlanningWorkflow
        from packages.packs.registry import PackRegistry
        from packages.planning.service import PlanningService

        service.planning = PlanningService(
            service,
            PlanningWorkflow(
                ClassifierAgent(
                    model, urgent_minutes=config.urgent_minutes, high_hours=config.high_hours
                ),
                PackRegistry(
                    Path(config.pack_directory),
                    deployed_demo_preview=config.deployed_demo_preview,
                ),
                environment=config.environment,
                demo_mode=config.demo_mode,
                allow_draft_preview=config.allow_draft_pack_preview,
            ),
        )
        if config.uk_pack_enabled:
            service.planning.workflow.registry.register_known("uk")
    if config.packets_enabled:
        from agents.packets import PacketPipeline, RetryPacketClient
        from packages.delivery import MockDeliveryService
        from packages.delivery.adapter import LocalMCPDeliveryAdapter
        from packages.packets.service import PacketService

        if service.planning is None:
            raise ValueError("Packet processing requires planning")
        mock = MockDeliveryService(
            repository,
            service.planning.workflow.registry,
            allow_draft_preview=config.allow_draft_pack_preview,
            environment=config.environment,
            demo_mode=config.demo_mode,
        )
        service.packets = PacketService(
            service,
            PacketPipeline(RetryPacketClient(model.for_packets()), timeout=35),
            LocalMCPDeliveryAdapter(mock),
        )
    if config.receiver_enabled:
        from agents.receiver import ReceiverBriefAgent
        from packages.receiver.bridge import DEMO_RECIPIENT_ORGS, ReceiverDecisionBridge
        from packages.receiver.service import ReceiverService

        if service.packets is None:
            raise ValueError("Receiver requires packet processing")
        service.receiver = ReceiverService(
            repository,
            recipient_orgs=DEMO_RECIPIENT_ORGS,
            hold_adapter=service.packets.adapter.place_hold,
            decision_bridge=ReceiverDecisionBridge(service, DEMO_RECIPIENT_ORGS),
            brief_maker=ReceiverBriefAgent(model).make_brief,
            clock=service.clock,
        )
        if config.a2a_receiver_url:
            from packages.receiver.handoff import ReceiverHandoffService
            from services.a2a_receiver.client import A2AHandoffClient

            service.receiver_handoff = ReceiverHandoffService(
                service,
                A2AHandoffClient(
                    config.a2a_receiver_url,
                    scope="victim-api",
                    runtime_mode="local" if config.environment == "local" else "cloud",
                ),
            )
    if config.sources_enabled:
        from packages.sources.fetch import OfficialFetcher
        from packages.sources.service import SourceService
        from packages.sources.storage import GoogleSourceStore, LocalSourceStore

        source_store = (
            GoogleSourceStore(
                StorageClient(project=config.gcp_project_id).bucket(config.bucket_sources)
            )
            if config.intake_storage_mode == "gcs"
            else LocalSourceStore(Path(config.intake_data_directory) / "sources")
        )
        service.sources = SourceService(
            repository,
            source_store,
            OfficialFetcher({host.strip() for host in config.allowed_fetch_domains.split(",")}),
            api_base_url=config.api_base_url,
            clock=service.clock,
        )
        if config.packstudio_enabled:
            from packages.packstudio import PackBuilderAdapter, PackStudioService

            service.packstudio = PackStudioService(
                service.sources, PackBuilderAdapter(model.for_packbuilder())
            )
            from packages.packs.durable import StudioCatalog

            service.planning.workflow.registry.studio_catalog = StudioCatalog(service.sources)
    if config.linking_enabled:
        from packages.linking.receiver import ReceiverLinks
        from packages.linking.runtime import catalog_hasher, load_cloud_key
        from packages.linking.service import LinkingService

        key = (
            local_signing_key(Path(config.intake_data_directory) / "linking")
            if config.environment == "local"
            else load_cloud_key(config.hmac_secret_name)
        )
        workflow = service.planning.workflow
        packs = workflow.registry.available(
            allow_draft_preview=workflow.allow_draft_preview,
            environment=workflow.environment,
            demo_mode=workflow.demo_mode,
        )
        service.linking = LinkingService(repository, catalog_hasher(key, packs))
        service.receiver_links = ReceiverLinks(service.linking, clock=service.clock)
    return service, model
