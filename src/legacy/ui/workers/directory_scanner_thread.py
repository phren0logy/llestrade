"""
Worker thread for scanning directories asynchronously.
Prevents UI freezing when dealing with large directories.
"""

import os

from PySide6.QtCore import QThread, Signal


class DirectoryScannerThread(QThread):
    """Worker thread for scanning directories without blocking the UI."""
    
    # Signals
    progress_signal = Signal(int, str)  # progress_percent, status_message
    files_found_signal = Signal(list)  # list of markdown files
    finished_signal = Signal(bool, str, list)  # success, message, files
    error_signal = Signal(str)  # error_message
    
    def __init__(self, directory_path, file_extensions=None):
        """
        Initialize the directory scanner thread.
        
        Args:
            directory_path: Path to the directory to scan
            file_extensions: List of file extensions to look for (default: ['.md'])
        """
        super().__init__()
        self.directory_path = directory_path
        self.file_extensions = file_extensions or ['.md']
        self.should_stop = False
        self.max_files_warning = 1000  # Warn if more than 1000 files
        
    def run(self):
        """Scan the directory for files with specified extensions."""
        try:
            if not os.path.exists(self.directory_path):
                self.error_signal.emit(f"Directory does not exist: {self.directory_path}")
                return
                
            if not os.path.isdir(self.directory_path):
                self.error_signal.emit(f"Path is not a directory: {self.directory_path}")
                return
            
            self.progress_signal.emit(10, f"Scanning directory: {os.path.basename(self.directory_path)}")
            
            # Get list of all files in directory
            try:
                all_files = os.listdir(self.directory_path)
            except PermissionError:
                self.error_signal.emit(f"Permission denied accessing directory: {self.directory_path}")
                return
            except Exception as e:
                self.error_signal.emit(f"Error reading directory: {str(e)}")
                return
            
            if self.should_stop:
                return
                
            self.progress_signal.emit(30, f"Found {len(all_files)} items, filtering...")
            
            # Filter for desired file extensions
            matching_files = []
            total_files = len(all_files)
            
            for i, filename in enumerate(all_files):
                if self.should_stop:
                    return
                    
                # Update progress every 100 files or at key intervals
                if i % 100 == 0 or i == total_files - 1:
                    progress = 30 + int((i / total_files) * 40)  # 30-70% for filtering
                    self.progress_signal.emit(progress, f"Checking file {i+1}/{total_files}")
                
                # Check if file has desired extension
                for ext in self.file_extensions:
                    if filename.lower().endswith(ext.lower()):
                        file_path = os.path.join(self.directory_path, filename)
                        # Verify it's actually a file
                        if os.path.isfile(file_path):
                            matching_files.append(file_path)
                        break
            
            if self.should_stop:
                return
                
            self.progress_signal.emit(80, f"Found {len(matching_files)} matching files, sorting...")
            
            # Sort files by modification time (newest first)
            # Do this in chunks to allow for cancellation
            if matching_files:
                try:
                    file_info = []
                    for i, file_path in enumerate(matching_files):
                        if self.should_stop:
                            return
                            
                        if i % 50 == 0:  # Update progress every 50 files
                            progress = 80 + int((i / len(matching_files)) * 15)  # 80-95% for sorting
                            self.progress_signal.emit(progress, f"Getting metadata {i+1}/{len(matching_files)}")
                        
                        try:
                            mtime = os.path.getmtime(file_path)
                            file_info.append((file_path, mtime))
                        except (OSError, IOError):
                            # If we can't get mtime, use current time
                            file_info.append((file_path, 0))
                    
                    # Sort by modification time
                    file_info.sort(key=lambda x: x[1], reverse=True)
                    matching_files = [item[0] for item in file_info]
                    
                except Exception as e:
                    self.error_signal.emit(f"Error sorting files: {str(e)}")
                    return
            
            if self.should_stop:
                return
                
            self.progress_signal.emit(100, f"Scan complete: {len(matching_files)} files found")
            
            # Check if we found too many files
            warning_message = ""
            if len(matching_files) > self.max_files_warning:
                warning_message = f"Warning: Large number of files ({len(matching_files)}) may impact performance"
            
            # Emit results
            self.files_found_signal.emit(matching_files)
            self.finished_signal.emit(True, warning_message, matching_files)
            
        except Exception as e:
            self.error_signal.emit(f"Unexpected error during directory scan: {str(e)}")
    
    def stop(self):
        """Stop the scanning operation."""
        self.should_stop = True 
