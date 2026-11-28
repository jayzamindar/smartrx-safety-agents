"""Enterprise OpenTelemetry observability and thread-safe in-memory metrics ledger."""

from __future__ import annotations

import importlib
import threading
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Protocol

from opentelemetry import metrics, trace
from opentelemetry.trace import Span, Status, StatusCode


class _Shutdownable(Protocol):
    def shutdown(self) -> None: ...


@dataclass(slots=True)
class LatencyStats:
    """Aggregated latency statistics (milliseconds) for an instrumented operation."""

    count: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0

    @property
    def avg_ms(self) -> float:
        return self.total_ms / self.count if self.count > 0 else 0.0


class InMemoryMetricsLedger:
    """Thread-safe in-memory accumulator for clinical reconciliation and audit metrics."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._batches_processed: int = 0
        self._resources_audited: int = 0
        self._alerts_flagged: int = 0
        self._quarantined_actions: int = 0
        self._escalations_triggered: int = 0
        self._counters: dict[str, int] = {}
        self._latencies: dict[str, LatencyStats] = {}

    def record_batch(
        self,
        *,
        resources_audited: int = 0,
        alerts_flagged: int = 0,
        quarantined_actions: int = 0,
        escalations_triggered: int = 0,
    ) -> None:
        """Atomically record a completed reconciliation batch."""
        with self._lock:
            self._batches_processed += 1
            self._resources_audited += max(0, resources_audited)
            self._alerts_flagged += max(0, alerts_flagged)
            self._quarantined_actions += max(0, quarantined_actions)
            self._escalations_triggered += max(0, escalations_triggered)

    def increment(self, name: str, amount: int = 1) -> int:
        """Increment a named counter atomically and return the updated value."""
        with self._lock:
            updated = self._counters.get(name, 0) + amount
            self._counters[name] = updated
            return updated

    def record_latency(self, operation: str, duration_ms: float) -> None:
        """Record an operation latency sample in milliseconds."""
        clamped = max(0.0, duration_ms)
        with self._lock:
            stats = self._latencies.get(operation)
            if stats is None:
                stats = LatencyStats()
                self._latencies[operation] = stats
            stats.count += 1
            stats.total_ms += clamped
            if clamped > stats.max_ms:
                stats.max_ms = clamped

    def snapshot(self) -> dict[str, Any]:
        """Return a thread-safe copy of all accumulated metrics."""
        with self._lock:
            return {
                "batches_processed": self._batches_processed,
                "resources_audited": self._resources_audited,
                "alerts_flagged": self._alerts_flagged,
                "quarantined_actions": self._quarantined_actions,
                "escalations_triggered": self._escalations_triggered,
                "counters": dict(self._counters),
                "latencies_ms": {
                    op: {
                        "count": st.count,
                        "total_ms": round(st.total_ms, 3),
                        "avg_ms": round(st.avg_ms, 3),
                        "max_ms": round(st.max_ms, 3),
                    }
                    for op, st in self._latencies.items()
                },
            }

    def reset(self) -> None:
        """Reset all in-memory counters and latency histograms."""
        with self._lock:
            self._batches_processed = 0
            self._resources_audited = 0
            self._alerts_flagged = 0
            self._quarantined_actions = 0
            self._escalations_triggered = 0
            self._counters.clear()
            self._latencies.clear()


@dataclass
class TelemetryManager:
    """Manages OpenTelemetry tracer/meter providers with deterministic shutdown."""

    service_name: str = "smartrx-safety-agents"
    metrics_ledger: InMemoryMetricsLedger = field(default_factory=InMemoryMetricsLedger)
    _tracer_provider: _Shutdownable | None = field(default=None, init=False, repr=False)
    _meter_provider: _Shutdownable | None = field(default=None, init=False, repr=False)
    _shutdown_called: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self._init_sdk_providers()
        self._tracer = trace.get_tracer(self.service_name)
        self._meter = metrics.get_meter(self.service_name)
        self._span_counter = self._meter.create_counter(
            name="smartrx.operations.count",
            description="Total instrumented operations executed.",
        )
        self._latency_histogram = self._meter.create_histogram(
            name="smartrx.operations.duration_ms",
            unit="ms",
            description="Operation latency in milliseconds.",
        )

    def _init_sdk_providers(self) -> None:
        try:
            sdk_trace = importlib.import_module("opentelemetry.sdk.trace")
            sdk_metrics = importlib.import_module("opentelemetry.sdk.metrics")
            tracer_cls = getattr(sdk_trace, "TracerProvider", None)
            meter_cls = getattr(sdk_metrics, "MeterProvider", None)
            if tracer_cls is not None:
                tp = tracer_cls()
                trace.set_tracer_provider(tp)
                self._tracer_provider = tp
            if meter_cls is not None:
                mp = meter_cls()
                metrics.set_meter_provider(mp)
                self._meter_provider = mp
        except ImportError:
            self._tracer_provider = None
            self._meter_provider = None

    @property
    def is_shutdown(self) -> bool:
        return self._shutdown_called

    def shutdown(self) -> None:
        """Flush and shut down attached OpenTelemetry providers."""
        if self._shutdown_called:
            return
        if self._tracer_provider is not None:
            self._tracer_provider.shutdown()
        if self._meter_provider is not None:
            self._meter_provider.shutdown()
        self._shutdown_called = True


_DEFAULT_MANAGER: TelemetryManager | None = None
_MANAGER_LOCK = threading.Lock()


def get_telemetry_manager() -> TelemetryManager:
    """Return the singleton TelemetryManager, initializing it on first access."""
    global _DEFAULT_MANAGER
    with _MANAGER_LOCK:
        if _DEFAULT_MANAGER is None or _DEFAULT_MANAGER.is_shutdown:
            _DEFAULT_MANAGER = TelemetryManager()
        return _DEFAULT_MANAGER


def get_metrics_ledger() -> InMemoryMetricsLedger:
    """Return the active in-memory metrics ledger."""
    return get_telemetry_manager().metrics_ledger


def shutdown_telemetry() -> None:
    """Shut down the active TelemetryManager (intended for app/test teardown)."""
    global _DEFAULT_MANAGER
    with _MANAGER_LOCK:
        if _DEFAULT_MANAGER is not None:
            _DEFAULT_MANAGER.shutdown()
            _DEFAULT_MANAGER = None


@contextmanager
def trace_span(
    name: str,
    attributes: Mapping[str, str | int | float | bool] | None = None,
    *,
    manager: TelemetryManager | None = None,
) -> Iterator[Span]:
    """Execute a block inside an OpenTelemetry span while tracking latency and counts."""
    mgr = manager or get_telemetry_manager()
    start = time.perf_counter()
    with mgr._tracer.start_as_current_span(name) as span:
        if attributes:
            for key, val in attributes.items():
                span.set_attribute(key, val)
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            mgr.metrics_ledger.increment(f"{name}.errors")
            raise
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            mgr.metrics_ledger.increment(f"{name}.calls")
            mgr.metrics_ledger.record_latency(name, elapsed_ms)
            mgr._span_counter.add(1, {"operation": name})
            mgr._latency_histogram.record(elapsed_ms, {"operation": name})
