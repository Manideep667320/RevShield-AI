"""
Circuit Breaker Implementation — Phase 6
Monitors downstream API (Razorpay) failure rates.
Opens circuit when failure rate exceeds threshold (20%), preventing cascading degradation.
"""
from collections import deque
from datetime import datetime, timedelta, timezone
from threading import Lock
from app.core.exceptions import CircuitOpenError
from app.core.logging import get_logger

logger = get_logger(__name__)


class CircuitBreaker:
    """Rolling-window circuit breaker for external service calls."""

    def __init__(self, window_size: int = 10, failure_threshold: float = 0.20, cooldown_seconds: int = 30):
        self.window_size = window_size
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.results: deque[bool] = deque(maxlen=window_size)
        self.is_open: bool = False
        self.opened_at: datetime | None = None
        self._lock = Lock()

    def check_state(self) -> None:
        """Verifies circuit state. Raises CircuitOpenError if circuit is currently open."""
        with self._lock:
            if self.is_open:
                if self.opened_at and (datetime.now(tz=timezone.utc) - self.opened_at).total_seconds() > self.cooldown_seconds:
                    logger.info("message=Circuit breaker cooling down -> entering HALF_OPEN state")
                    self.is_open = False
                    self.opened_at = None
                else:
                    logger.warning("message=Circuit breaker is OPEN -> rejecting request")
                    raise CircuitOpenError("Circuit breaker is OPEN due to downstream Razorpay error rate > 20%")

    def record_success(self) -> None:
        """Records a successful call."""
        with self._lock:
            self.results.append(True)
            self._evaluate_threshold()

    def record_failure(self) -> None:
        """Records a failed call."""
        with self._lock:
            self.results.append(False)
            self._evaluate_threshold()

    def _evaluate_threshold(self) -> None:
        if len(self.results) >= self.window_size:
            failures = self.results.count(False)
            rate = failures / float(self.window_size)
            if rate > self.failure_threshold:
                self.is_open = True
                self.opened_at = datetime.now(tz=timezone.utc)
                logger.error(f"message=Circuit breaker OPENED | failure_rate={rate*100:.1f}% | threshold={self.failure_threshold*100:.1f}%")

    def reset(self) -> None:
        """Resets circuit breaker state."""
        with self._lock:
            self.results.clear()
            self.is_open = False
            self.opened_at = None


# Shared singleton instance for Razorpay API calls
razorpay_circuit_breaker = CircuitBreaker()
