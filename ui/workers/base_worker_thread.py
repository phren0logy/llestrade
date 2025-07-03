"""
Enhanced base class for worker threads with robust error handling.
Provides retry logic, cancellation support, and detailed operation tracking.
"""

from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker
import logging
import traceback
import time
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, Callable, TypeVar, Generic

T = TypeVar('T')


class BaseWorkerThread(QThread):
    """Enhanced base class for worker threads with robust error handling."""
    
    # Signals
    progress_signal = Signal(int, str)  # progress, message
    error_signal = Signal(str, dict)    # error_message, error_details
    warning_signal = Signal(str)        # warning_message
    debug_signal = Signal(str)          # debug_message
    status_signal = Signal(dict)        # status_dict
    
    def __init__(self, parent=None, operation_name: str = None):
        super().__init__(parent)
        self.operation_name = operation_name or self.__class__.__name__
        self.logger = logging.getLogger(f"{self.__class__.__module__}.{self.__class__.__name__}")
        
        # Operation tracking
        self._operation_id = None
        self._start_time = None
        self._is_cancelled = False
        self._mutex = QMutex()
        
        # Retry configuration
        self.max_retries = 3
        self.retry_delay = 1.0  # seconds
        self.retry_backoff = 2.0  # exponential backoff multiplier
        
    def run(self):
        """Base run method - subclasses should call super().run() first."""
        self._start_time = time.time()
        self._operation_id = f"{self.operation_name}_{uuid.uuid4().hex[:8]}"
        self._is_cancelled = False
        
        self.logger.info(
            f"Starting operation: {self._operation_id}",
            extra={'operation_id': self._operation_id}
        )
        
        try:
            self._emit_status("started")
        except Exception as e:
            self.logger.error(f"Failed to emit start status: {e}")
            
    def cancel(self):
        """Request cancellation of the operation."""
        with QMutexLocker(self._mutex):
            self._is_cancelled = True
        self.logger.info(f"Cancellation requested for {self._operation_id}")
        
    def is_cancelled(self) -> bool:
        """Check if cancellation was requested."""
        with QMutexLocker(self._mutex):
            return self._is_cancelled
            
    def safe_emit(self, signal: Signal, *args):
        """Safely emit a signal with error handling."""
        try:
            if not self.is_cancelled():
                signal.emit(*args)
        except Exception as e:
            self.logger.error(
                f"Error emitting signal {signal}: {e}",
                exc_info=True
            )
            
    def handle_error(self, error: Exception, context: Optional[Dict[str, Any]] = None):
        """Standardized error handling for worker threads."""
        error_details = {
            'type': type(error).__name__,
            'message': str(error),
            'traceback': traceback.format_exc(),
            'operation_id': self._operation_id,
            'operation_name': self.operation_name,
            'elapsed_time': time.time() - self._start_time if self._start_time else 0,
            'context': context or {},
            'timestamp': datetime.now().isoformat()
        }
        
        # Log with full context
        self.logger.error(
            f"Error in {self.operation_name}: {error}",
            extra=error_details,
            exc_info=True
        )
        
        # Emit error signal
        self.safe_emit(self.error_signal, str(error), error_details)
        self._emit_status("error", error_details)
        
    def retry_operation(self, operation: Callable[..., T], *args, **kwargs) -> T:
        """Execute an operation with retry logic."""
        last_error = None
        delay = self.retry_delay
        
        for attempt in range(self.max_retries):
            if self.is_cancelled():
                break
                
            try:
                return operation(*args, **kwargs)
            except Exception as e:
                last_error = e
                self.logger.warning(
                    f"Attempt {attempt + 1}/{self.max_retries} failed: {e}",
                    extra={'operation_id': self._operation_id}
                )
                
                if attempt < self.max_retries - 1:
                    self.safe_emit(
                        self.warning_signal,
                        f"Retrying in {delay}s... (attempt {attempt + 2}/{self.max_retries})"
                    )
                    time.sleep(delay)
                    delay *= self.retry_backoff
                    
        # All retries failed
        raise last_error
        
    def _emit_status(self, status: str, details: Optional[Dict] = None):
        """Emit a status update."""
        status_dict = {
            'status': status,
            'operation_id': self._operation_id,
            'operation_name': self.operation_name,
            'elapsed_time': time.time() - self._start_time if self._start_time else 0,
            'timestamp': datetime.now().isoformat()
        }
        
        if details:
            status_dict.update(details)
            
        self.safe_emit(self.status_signal, status_dict)
        
    def cleanup(self):
        """Cleanup method called when thread finishes."""
        self._emit_status("finished")
        elapsed = time.time() - self._start_time if self._start_time else 0
        self.logger.info(
            f"Operation {self._operation_id} completed in {elapsed:.2f}s",
            extra={'operation_id': self._operation_id, 'elapsed_time': elapsed}
        )
        
    def emit_progress(self, progress: int, message: str = ""):
        """Emit progress update with optional message."""
        self.safe_emit(self.progress_signal, progress, message)
        if message:
            self.logger.debug(f"Progress {progress}%: {message}")
            
    def emit_warning(self, message: str):
        """Emit a warning message."""
        self.safe_emit(self.warning_signal, message)
        self.logger.warning(message)
        
    def emit_debug(self, message: str):
        """Emit a debug message."""
        self.safe_emit(self.debug_signal, message)
        self.logger.debug(message)