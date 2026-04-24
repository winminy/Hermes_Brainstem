from __future__ import annotations

from plugins.memory.hermes_memory.attach import PersistAttachPipeline
from plugins.memory.hermes_memory.backends.embedding import EmbeddingBackend, build_embedding_backend
from plugins.memory.hermes_memory.backends.lightrag import LightRAGBackend, LightRAGHTTPBackend
from plugins.memory.hermes_memory.backends.notion import NotionBackend
from plugins.memory.hermes_memory.config import ConfigLayer, HermesMemorySettings
from plugins.memory.hermes_memory.core.clock import Clock
from plugins.memory.hermes_memory.inbox import InboxClassifier, InboxDeduplicator, InboxGraduator, InboxRunner
from plugins.memory.hermes_memory.pipeline import PersistProcessPipeline


class HermesMemoryServices:
    def __init__(
        self,
        *,
        config: ConfigLayer | None = None,
        settings: HermesMemorySettings | None = None,
        notion_backend: NotionBackend | None = None,
        embedding_backend: EmbeddingBackend | None = None,
        lightrag_backend: LightRAGBackend | None = None,
        pipeline: PersistProcessPipeline | None = None,
        inbox_runner: InboxRunner | None = None,
        attach_pipeline: PersistAttachPipeline | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.config = config or ConfigLayer.from_settings(settings)
        self._clock = clock
        self._notion_backend = notion_backend
        self._embedding_backend = embedding_backend
        self._lightrag_backend = lightrag_backend
        self._pipeline = pipeline
        self._inbox_runner = inbox_runner
        self._attach_pipeline = attach_pipeline

    @property
    def notion_backend(self) -> NotionBackend:
        if self._notion_backend is None:
            self._notion_backend = NotionBackend(config=self.config)
        return self._notion_backend

    @property
    def embedding_backend(self) -> EmbeddingBackend:
        if self._embedding_backend is None:
            self._embedding_backend = build_embedding_backend(self.config)
        return self._embedding_backend

    @property
    def lightrag_backend(self) -> LightRAGBackend:
        if self._lightrag_backend is None:
            self._lightrag_backend = LightRAGHTTPBackend(config=self.config, embedding_backend=self.embedding_backend)
        return self._lightrag_backend

    @property
    def pipeline(self) -> PersistProcessPipeline:
        if self._pipeline is None:
            self._pipeline = PersistProcessPipeline(
                config=self.config,
                notion_backend=self.notion_backend,
                embedding_backend=self.embedding_backend,
                lightrag_backend=self.lightrag_backend,
                clock=self._clock,
            )
        return self._pipeline

    @property
    def inbox_runner(self) -> InboxRunner:
        if self._inbox_runner is None:
            self._inbox_runner = InboxRunner(
                self.config,
                deduplicator=InboxDeduplicator(self.config, lightrag_backend=self.lightrag_backend, clock=self._clock),
                classifier=InboxClassifier(self.config),
                graduator=InboxGraduator(self.config, pipeline=self.pipeline),
                notion_backend=self.notion_backend,
                pipeline=self.pipeline,
                clock=self._clock,
            )
        return self._inbox_runner

    @property
    def attach_pipeline(self) -> PersistAttachPipeline:
        if self._attach_pipeline is None:
            self._attach_pipeline = PersistAttachPipeline(
                config=self.config,
                notion_backend=self.notion_backend,
                inbox_runner=self.inbox_runner,
                clock=self._clock,
            )
        return self._attach_pipeline
