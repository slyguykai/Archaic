"""
Logging and Error Handling System

This module provides centralized logging configuration and error handling
utilities for the Archaic web scraper application.
"""

import logging
import logging.handlers
import os
import sys
from datetime import datetime
from typing import Optional, Dict, Any
import traceback
from pathlib import Path


class ArchaicLogger:
    """
    Centralized logging system for the Archaic application.
    
    Provides structured logging with different levels, file rotation,
    and error tracking capabilities.
    """
    
    def __init__(self, log_dir: str = "logs", app_name: str = "archaic"):
        """
        Initialize the logging system.
        
        Args:
            log_dir: Directory to store log files
            app_name: Name of the application for log formatting
        """
        self.log_dir = Path(log_dir)
        self.app_name = app_name
        self.loggers: Dict[str, logging.Logger] = {}
        
        # Ensure log directory exists
        self.log_dir.mkdir(exist_ok=True)
        
        # Setup main application logger
        self.setup_logger()
    
    def setup_logger(self, level: int = logging.INFO) -> logging.Logger:
        """
        Set up the main application logger with file and console handlers.
        
        Args:
            level: Logging level (default: INFO)
            
        Returns:
            Configured logger instance
        """
        # Create main logger
        logger = logging.getLogger(self.app_name)
        logger.setLevel(level)
        
        # Prevent duplicate handlers
        if logger.handlers:
            return logger
        
        # Create formatters
        detailed_formatter = logging.Formatter(
            '%(asctime)s | %(name)s | %(levelname)s | %(funcName)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        console_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%H:%M:%S'
        )
        
        # File handler with rotation
        log_file = self.log_dir / f"{self.app_name}.log"
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(detailed_formatter)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(console_formatter)
        
        # Error file handler
        error_file = self.log_dir / f"{self.app_name}_errors.log"
        error_handler = logging.handlers.RotatingFileHandler(
            error_file,
            maxBytes=5*1024*1024,  # 5MB
            backupCount=3,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(detailed_formatter)
        
        # Add handlers to logger
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        logger.addHandler(error_handler)
        
        self.loggers['main'] = logger
        return logger
    
    def get_logger(self, name: str) -> logging.Logger:
        """
        Get a logger for a specific module.
        
        Args:
            name: Name of the module/component
            
        Returns:
            Logger instance for the module
        """
        full_name = f"{self.app_name}.{name}"
        
        if full_name not in self.loggers:
            logger = logging.getLogger(full_name)
            logger.setLevel(logging.DEBUG)
            self.loggers[full_name] = logger
        
        return self.loggers[full_name]
    
    def create_session_log(self, session_id: str) -> str:
        """
        Create a session-specific log file.
        
        Args:
            session_id: Unique identifier for the session
            
        Returns:
            Path to the session log file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_log_file = self.log_dir / f"session_{session_id}_{timestamp}.log"
        
        # Create session logger
        session_logger = logging.getLogger(f"{self.app_name}.session.{session_id}")
        session_logger.setLevel(logging.DEBUG)
        
        # Session file handler
        session_handler = logging.FileHandler(session_log_file, encoding='utf-8')
        session_handler.setLevel(logging.DEBUG)
        
        session_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        session_handler.setFormatter(session_formatter)
        
        session_logger.addHandler(session_handler)
        self.loggers[f"session.{session_id}"] = session_logger
        
        return str(session_log_file)
    
    def log_system_info(self):
        """Log system information for debugging."""
        logger = self.get_logger('system')
        
        logger.info("=== Archaic Application Started ===")
        logger.info(f"Python version: {sys.version}")
        logger.info(f"Platform: {sys.platform}")
        logger.info(f"Working directory: {os.getcwd()}")
        logger.info(f"Log directory: {self.log_dir.absolute()}")


class ErrorTracker:
    """
    Tracks and categorizes errors that occur during operation.
    """
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.errors: list = []
        self.warnings: list = []
    
    def log_error(self, 
                  error: Exception, 
                  context: str = None, 
                  url: str = None,
                  additional_info: Dict[str, Any] = None) -> str:
        """
        Log an error with context information.
        
        Args:
            error: The exception that occurred
            context: Context where the error occurred
            url: URL being processed when error occurred
            additional_info: Additional information about the error
            
        Returns:
            Error ID for tracking
        """
        error_id = f"ERR_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.errors):03d}"
        
        error_data = {
            'id': error_id,
            'timestamp': datetime.now(),
            'type': type(error).__name__,
            'message': str(error),
            'context': context,
            'url': url,
            'traceback': traceback.format_exc(),
            'additional_info': additional_info or {}
        }
        
        self.errors.append(error_data)
        
        # Log the error
        log_message = f"[{error_id}] {error_data['type']}: {error_data['message']}"
        if context:
            log_message += f" (Context: {context})"
        if url:
            log_message += f" (URL: {url})"
        
        self.logger.error(log_message)
        self.logger.debug(f"[{error_id}] Full traceback:\n{error_data['traceback']}")
        
        return error_id
    
    def log_warning(self, 
                    message: str, 
                    context: str = None, 
                    url: str = None) -> str:
        """
        Log a warning with context information.
        
        Args:
            message: Warning message
            context: Context where the warning occurred
            url: URL being processed when warning occurred
            
        Returns:
            Warning ID for tracking
        """
        warning_id = f"WARN_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.warnings):03d}"
        
        warning_data = {
            'id': warning_id,
            'timestamp': datetime.now(),
            'message': message,
            'context': context,
            'url': url
        }
        
        self.warnings.append(warning_data)
        
        # Log the warning
        log_message = f"[{warning_id}] {message}"
        if context:
            log_message += f" (Context: {context})"
        if url:
            log_message += f" (URL: {url})"
        
        self.logger.warning(log_message)
        
        return warning_id
    
    def get_error_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all errors and warnings.
        
        Returns:
            Dictionary with error statistics and details
        """
        return {
            'total_errors': len(self.errors),
            'total_warnings': len(self.warnings),
            'error_types': self._count_error_types(),
            'recent_errors': self.errors[-5:] if self.errors else [],
            'recent_warnings': self.warnings[-5:] if self.warnings else []
        }
    
    def _count_error_types(self) -> Dict[str, int]:
        """Count errors by type."""
        type_counts = {}
        for error in self.errors:
            error_type = error['type']
            type_counts[error_type] = type_counts.get(error_type, 0) + 1
        return type_counts
    
    def save_error_report(self, output_path: str):
        """
        Save a detailed error report to a file.
        
        Args:
            output_path: Path where the report should be saved
        """
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write("ARCHAIC ERROR REPORT\n")
                f.write("=" * 50 + "\n\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Total Errors: {len(self.errors)}\n")
                f.write(f"Total Warnings: {len(self.warnings)}\n\n")
                
                if self.errors:
                    f.write("ERRORS:\n")
                    f.write("-" * 30 + "\n")
                    for error in self.errors:
                        f.write(f"\n[{error['id']}] {error['timestamp']}\n")
                        f.write(f"Type: {error['type']}\n")
                        f.write(f"Message: {error['message']}\n")
                        if error['context']:
                            f.write(f"Context: {error['context']}\n")
                        if error['url']:
                            f.write(f"URL: {error['url']}\n")
                        f.write(f"Traceback:\n{error['traceback']}\n")
                        f.write("-" * 50 + "\n")
                
                if self.warnings:
                    f.write("\nWARNINGS:\n")
                    f.write("-" * 30 + "\n")
                    for warning in self.warnings:
                        f.write(f"\n[{warning['id']}] {warning['timestamp']}\n")
                        f.write(f"Message: {warning['message']}\n")
                        if warning['context']:
                            f.write(f"Context: {warning['context']}\n")
                        if warning['url']:
                            f.write(f"URL: {warning['url']}\n")
                        f.write("-" * 30 + "\n")
            
            self.logger.info(f"Error report saved to: {output_path}")
            
        except Exception as e:
            self.logger.error(f"Failed to save error report: {e}")


# Global logger instance
_logger_instance: Optional[ArchaicLogger] = None


def get_logger(name: str = None) -> logging.Logger:
    """
    Get a logger instance.
    
    Args:
        name: Name of the module/component (optional)
        
    Returns:
        Logger instance
    """
    global _logger_instance
    
    if _logger_instance is None:
        _logger_instance = ArchaicLogger()
    
    if name:
        return _logger_instance.get_logger(name)
    else:
        return _logger_instance.get_logger('main')


def initialize_logging(log_dir: str = "logs", level: int = logging.INFO):
    """
    Initialize the global logging system.
    
    Args:
        log_dir: Directory for log files
        level: Logging level
    """
    global _logger_instance
    _logger_instance = ArchaicLogger(log_dir)
    _logger_instance.setup_logger(level)
    _logger_instance.log_system_info()


def create_error_tracker(logger_name: str = None) -> ErrorTracker:
    """
    Create an error tracker instance.
    
    Args:
        logger_name: Name of the logger to use
        
    Returns:
        ErrorTracker instance
    """
    logger = get_logger(logger_name)
    return ErrorTracker(logger)