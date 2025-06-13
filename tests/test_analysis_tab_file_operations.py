import os
import unittest
from unittest.mock import MagicMock, call, mock_open, patch

# --- Begin Comprehensive Mocking Setup ---

# 1. Define individual Qt component mocks
mock_qwidget = MagicMock()
mock_qapplication = MagicMock()
mock_qlabel = MagicMock()
mock_qlineedit = MagicMock()
mock_qtextedit = MagicMock()
mock_qcombobox = MagicMock()
mock_qpushbutton = MagicMock()

mock_qstyle_class_obj = MagicMock() # Mock for the QStyle class itself
mock_qstyle_instance = MagicMock() # Mock for an instance of QStyle
mock_qstyle_class_obj.return_value = mock_qstyle_instance # QStyle() returns our instance mock
mock_qstyle_instance.standardIcon = MagicMock() # Instance has standardIcon method

mock_qgroupbox = MagicMock()
mock_qvboxlayout = MagicMock()
mock_qhboxlayout = MagicMock()
mock_qformlayout = MagicMock()
mock_qfiledialog = MagicMock()
mock_qmessagebox = MagicMock()
mock_qprogressdialog = MagicMock()
mock_qfont = MagicMock()
mock_qt = MagicMock()
mock_qthread = MagicMock()

# Mock for the QTimer class object, with a mock for its static/class method singleShot
mock_qtimer_class_obj = MagicMock() # Removed spec_set=type
mock_qtimer_class_obj.singleShot = MagicMock()

# List of fundamental Qt class mocks for easy reset
qt_class_mocks = [
    mock_qwidget, mock_qapplication, mock_qlabel, mock_qlineedit,
    mock_qtextedit, mock_qcombobox, mock_qpushbutton, mock_qstyle_class_obj,
    mock_qgroupbox, mock_qvboxlayout, mock_qhboxlayout, mock_qformlayout,
    mock_qfiledialog, mock_qmessagebox, mock_qprogressdialog, mock_qfont,
    mock_qt, mock_qthread, mock_qtimer_class_obj
]

# 2. Create mocks for PySide6 submodules
mock_qt_widgets = MagicMock()
mock_qt_gui = MagicMock()
mock_qt_core = MagicMock()

# Assign components to PySide6.QtWidgets mock
mock_qt_widgets.QWidget = mock_qwidget
mock_qt_widgets.QApplication = mock_qapplication
mock_qt_widgets.QLabel = mock_qlabel
mock_qt_widgets.QLineEdit = mock_qlineedit
mock_qt_widgets.QTextEdit = mock_qtextedit
mock_qt_widgets.QComboBox = mock_qcombobox
mock_qt_widgets.QPushButton = mock_qpushbutton
mock_qt_widgets.QStyle = mock_qstyle_class_obj # Assign the QStyle class mock here
mock_qt_widgets.QGroupBox = mock_qgroupbox
mock_qt_widgets.QVBoxLayout = mock_qvboxlayout
mock_qt_widgets.QHBoxLayout = mock_qhboxlayout
mock_qt_widgets.QFormLayout = mock_qformlayout
mock_qt_widgets.QFileDialog = mock_qfiledialog
mock_qt_widgets.QMessageBox = mock_qmessagebox
mock_qt_widgets.QProgressDialog = mock_qprogressdialog

# Assign components to PySide6.QtGui mock
mock_qt_gui.QFont = mock_qfont
mock_qt_gui.QAction = MagicMock()

# Assign components to PySide6.QtCore mock
mock_qt_core.Qt = mock_qt
mock_qt_core.Signal = MagicMock # Class, not instance
mock_qt_core.QThread = mock_qthread # Class, not instance
mock_qt_core.QTimer = mock_qtimer_class_obj # Assign the QTimer class mock here

# 3. Prepare dictionary for sys.modules patching
mocked_modules_dict = {
    'PySide6.QtWidgets': mock_qt_widgets,
    'PySide6.QtGui': mock_qt_gui,
    'PySide6.QtCore': mock_qt_core,
    'app_config': MagicMock(
        get_available_providers_and_models=MagicMock(return_value=[
            {'id': 'provider1', 'model': 'model1-test', 'display_name': 'Provider 1 / Model 1'}
        ]),
        get_configured_llm_client=MagicMock()
    ),
    'config': MagicMock(
        DEFAULT_FONT_FAMILY='Arial',
        DEFAULT_FONT_SIZE=12
    ),
    'llm_utils': MagicMock(
        LLMClientFactory=MagicMock(),
        cached_count_tokens=MagicMock(return_value=10)
    ),
    'ui.base_tab': MagicMock(BaseTab=mock_qwidget),
    'ui.components.file_selector': MagicMock(FileSelector=MagicMock()),
    'ui.components.status_panel': MagicMock(StatusPanel=MagicMock()),
    'ui.components.workflow_indicator': MagicMock(WorkflowIndicator=MagicMock(), WorkflowStep=MagicMock()),
    'ui.workers.llm_summary_thread': MagicMock(),
    'ui.workers.integrated_analysis_thread': MagicMock(),
}

# 4. Apply all mocks to sys.modules
sys_modules_patch = patch.dict('sys.modules', mocked_modules_dict)
sys_modules_patch.start()

# --- End Comprehensive Mocking Setup ---

# Import QTimer and other necessities AFTER sys.modules is patched
# from PySide6.QtCore import QTimer # No longer needed here if analysis_tab imports it
from ui.analysis_tab import COMBINED_SUMMARY_FILENAME, SUMMARIES_SUBDIR, AnalysisTab


class TestAnalysisTabFileOperations(unittest.TestCase):

    @classmethod
    def tearDownClass(cls):
        sys_modules_patch.stop()

    @patch('os.path.exists')
    @patch('os.listdir')
    @patch('os.makedirs')
    @patch('builtins.open', new_callable=mock_open)
    @patch('ui.analysis_tab.LLMSummaryThread')
    # No longer patch QTimer via decorator here, rely on sys.modules mock
    def setUp(self, MockLLMSummaryThreadFromDecorator, mock_open_func, mock_makedirs, mock_listdir, mock_path_exists):
        
        # Reset side_effect for all shared Qt class mocks to prevent state leakage
        for m in qt_class_mocks:
            m.reset_mock(return_value=True, side_effect=True) # Reset all, including side_effect

        # Also reset specific mocks that might have specific configurations like return_value
        mock_qstyle_class_obj.return_value = mock_qstyle_instance # Re-assert this after reset
        mock_qstyle_instance.standardIcon.reset_mock()
        mock_qtimer_class_obj.singleShot.reset_mock()
        
        # Reset mocks for other UI components if they are stateful and defined globally
        # For now, assuming FileSelector(), StatusPanel(), WorkflowIndicator() return fresh MagicMocks
        # from the sys.modules setup, so their internal state shouldn't leak unless their class mocks
        # (e.g. mocked_modules_dict['ui.components.file_selector'].FileSelector) are modified.

        self.mock_parent = mock_qt_widgets.QWidget() # Use the QWidget mock from PySide6.QtWidgets mock
        self.mock_status_bar = MagicMock()
        
        # Instantiate AnalysisTab first
        # AnalysisTab is imported at the module level. Its __init__ will be called.
        # Its BaseTab will be mock_qwidget. QWidget.style() is a real method.
        # We will replace the style method on the *instance* self.tab.
        self.tab = AnalysisTab(parent=self.mock_parent, status_bar=self.mock_status_bar)
        
        # Directly mock the style() method on the instance to return our mock_qstyle_instance
        # This mock_qstyle_instance is already configured with a standardIcon mock.
        self.tab.style = MagicMock(return_value=mock_qstyle_instance)

        self.mock_open = mock_open_func
        self.mock_makedirs = mock_makedirs
        self.mock_listdir = mock_listdir
        self.mock_path_exists = mock_path_exists
        self.MockLLMSummaryThread = MockLLMSummaryThreadFromDecorator
        # Explicitly reset side_effect for the LLMSummaryThread mock for each test setup
        # Tests that need a specific side_effect (like an iterable) will set it themselves.
        self.MockLLMSummaryThread.side_effect = None 
        self.MockLLMSummaryThread.return_value = MagicMock() # Default behavior is to return a new MagicMock
        
        self.tab.markdown_directory = "/fake/markdown_dir"
        self.tab.results_output_directory = "/fake/results_dir"
        self.tab.selected_llm_provider_id = "provider1"
        self.tab.selected_llm_model_name = "model1-test"
        
        # Mock UI elements if they are directly accessed for properties like text()
        self.tab.subject_input = MagicMock()
        self.tab.subject_input.text.return_value = "John Doe"
        self.tab.dob_input = MagicMock()
        self.tab.dob_input.text.return_value = "2000-01-01"
        self.tab.case_info_input = MagicMock()
        self.tab.case_info_input.toPlainText.return_value = "Test case."
        self.tab.llm_process_button = MagicMock()
        self.tab.combine_button = MagicMock()
        self.tab.integrate_button = MagicMock()
        self.tab.status_panel = MagicMock()
        self.tab.workflow_indicator = MagicMock()
        self.tab.file_selector = MagicMock()
        self.tab.preview_area = MagicMock()
        
        self.mock_path_exists.return_value = True 
        self.mock_listdir.return_value = []
        # Ensure open mock is clean for each test
        self.mock_open.reset_mock()

    def tearDown(self):
        patch.stopall() # Stops method-level patches

    def test_summarize_with_llm_writes_to_summaries_subdir(self):
        self.mock_listdir.side_effect = [
            ["annual_report.md", "project_alpha.v2.doc.md"], # New input filenames
            [] 
        ]

        expected_summaries_output_dir = os.path.join(self.tab.results_output_directory, SUMMARIES_SUBDIR)
        # Updated expected summary file paths
        mock_report_summary_path = os.path.join(expected_summaries_output_dir, "annual_report_summary.md")
        mock_project_summary_path = os.path.join(expected_summaries_output_dir, "project_alpha.v2.doc_summary.md")

        def path_exists_logic(path_arg):
            if path_arg == self.tab.markdown_directory: return True
            if path_arg == self.tab.results_output_directory: return True
            # Check against new summary paths
            if path_arg == mock_report_summary_path or path_arg == mock_project_summary_path:
                return False 
            if path_arg == expected_summaries_output_dir: 
                return False 
            return False 
        self.mock_path_exists.side_effect = path_exists_logic

        mock_thread_instance_report = MagicMock(name="ThreadReport")
        mock_thread_instance_project = MagicMock(name="ThreadProject")

        mock_thread_instance_report.start = MagicMock(
            side_effect=lambda: self.mock_open(mock_report_summary_path, "w").write("Summary for Annual Report")
        )
        mock_thread_instance_project.start = MagicMock(
            side_effect=lambda: self.mock_open(mock_project_summary_path, "w").write("Summary for Project Alpha v2")
        )

        self.MockLLMSummaryThread.side_effect = [mock_thread_instance_report, mock_thread_instance_project]

        self.tab.summarize_with_llm() 

        for i in range(3): 
            if not mock_qtimer_class_obj.singleShot.called: break
            args, kwargs = mock_qtimer_class_obj.singleShot.call_args
            callback_func = args[0]
            mock_qtimer_class_obj.singleShot.reset_mock() 
            self.mock_path_exists.side_effect = path_exists_logic 
            callback_func() 
            if callback_func.__name__ == 'finish_processing': break
        
        self.mock_makedirs.assert_called_with(expected_summaries_output_dir, exist_ok=True)
        self.assertEqual(self.MockLLMSummaryThread.call_count, 2, "LLMSummaryThread should be called for each file")

        expected_thread_calls = [
            call(
                self.tab, 
                markdown_files=[os.path.join(self.tab.markdown_directory, "annual_report.md")], # Updated
                output_dir=expected_summaries_output_dir,
                subject_name="John Doe",
                subject_dob="2000-01-01",
                case_info="Test case.",
                status_panel=self.tab.status_panel,
                llm_provider_id="provider1",
                llm_model_name="model1-test"
            ),
            call(
                self.tab, 
                markdown_files=[os.path.join(self.tab.markdown_directory, "project_alpha.v2.doc.md")], # Updated
                output_dir=expected_summaries_output_dir,
                subject_name="John Doe",
                subject_dob="2000-01-01",
                case_info="Test case.",
                status_panel=self.tab.status_panel,
                llm_provider_id="provider1",
                llm_model_name="model1-test"
            )
        ]
        self.MockLLMSummaryThread.assert_has_calls(expected_thread_calls, any_order=False)

        mock_thread_instance_report.start.assert_called_once()
        mock_thread_instance_project.start.assert_called_once()

        self.mock_open.assert_any_call(mock_report_summary_path, "w")
        self.mock_open.assert_any_call(mock_project_summary_path, "w")
        
        self.mock_open(mock_report_summary_path, "w").write.assert_called_once_with("Summary for Annual Report")
        self.mock_open(mock_project_summary_path, "w").write.assert_called_once_with("Summary for Project Alpha v2")


    def test_combine_summaries_reads_from_subdir_writes_to_root(self):
        summaries_dir = os.path.join(self.tab.results_output_directory, SUMMARIES_SUBDIR)
        # Updated summary file names to match new convention and test cases
        summary_file_names = ["annual_report_summary.md", "project_alpha.v2.doc_summary.md"]
        full_summary_paths = [os.path.join(summaries_dir, fname) for fname in summary_file_names]
        
        def path_exists_side_effect_for_combine(path):
            if path == self.tab.results_output_directory: return True
            if path == summaries_dir: return True
            return False 
        self.mock_path_exists.side_effect = path_exists_side_effect_for_combine
        
        self.mock_listdir.return_value = summary_file_names 

        mock_progress_dialog_instance = MagicMock()
        mock_qprogressdialog.return_value = mock_progress_dialog_instance 

        mock_report_content = "Summary for Annual Report"
        mock_project_content = "Summary for Project Alpha v2.doc"
        
        mock_write_handle = mock_open().return_value 

        def open_side_effect(file_path, mode, encoding=None):
            if file_path == full_summary_paths[0] and mode == "r":
                return mock_open(read_data=mock_report_content).return_value
            elif file_path == full_summary_paths[1] and mode == "r":
                return mock_open(read_data=mock_project_content).return_value
            elif file_path == os.path.join(self.tab.results_output_directory, COMBINED_SUMMARY_FILENAME) and mode == "w":
                return mock_write_handle
            print(f"Unexpected open call: {file_path}, {mode}")
            return mock_open().return_value 
        self.mock_open.side_effect = open_side_effect
        
        # Reset QMessageBox.warning mock before the call
        mock_qmessagebox.warning.reset_mock()

        self.tab.combine_summaries()

        # Check if QMessageBox.warning was called (for debugging the listdir issue)
        if mock_qmessagebox.warning.called:
            print("DEBUG: QMessageBox.warning WAS CALLED in combine_summaries")
            print(f"  Call args: {mock_qmessagebox.warning.call_args}")
        else:
            print("DEBUG: QMessageBox.warning WAS NOT CALLED in combine_summaries")

        self.mock_listdir.assert_called_once_with(summaries_dir)

        self.mock_open.assert_any_call(full_summary_paths[0], "r", encoding="utf-8")
        self.mock_open.assert_any_call(full_summary_paths[1], "r", encoding="utf-8")

        expected_combined_file_path = os.path.join(self.tab.results_output_directory, COMBINED_SUMMARY_FILENAME)
        self.mock_open.assert_any_call(expected_combined_file_path, "w", encoding="utf-8")
        
        written_content_calls = mock_write_handle.write.call_args_list
        written_content = "".join(c[0][0] for c in written_content_calls)

        self.assertIn(mock_report_content, written_content)
        self.assertIn(mock_project_content, written_content)
        self.assertIn(f"# Combined Summary for {self.tab.subject_input.text()}", written_content)
        self.assertIn(f"Date of Birth: {self.tab.dob_input.text()}", written_content)
        self.assertIn(f"Case Information:\n\n{self.tab.case_info_input.toPlainText()}", written_content)
        # Verify extracted basenames (original filenames without _summary.md)
        self.assertIn("### annual_report", written_content)
        self.assertIn("### project_alpha.v2.doc", written_content)
        
        mock_qprogressdialog.assert_called_once()
        mock_progress_dialog_instance.show.assert_called_once()
        self.assertTrue(mock_qtimer_class_obj.singleShot.called)
        args, _ = mock_qtimer_class_obj.singleShot.call_args
        timer_callback = args[0]
        self.assertEqual(timer_callback, mock_progress_dialog_instance.close)

    @patch('ui.analysis_tab.IntegratedAnalysisThread') 
    def test_generate_integrated_analysis_reads_combined_from_summaries_subdir(self, MockIntegratedAnalysisThread):
        # Determine the expected path for the combined summary file, which is now in the SUMMARIES_SUBDIR
        subject_name = self.tab.subject_input.text() # Mocked to "John Doe"
        # As per AnalysisTab.generate_integrated_analysis logic:
        combined_summary_filename = f"{subject_name}_Combined_Summaries.md" if subject_name else "Combined_Summaries.md"
        expected_combined_summary_path = os.path.join(self.tab.results_output_directory, SUMMARIES_SUBDIR, combined_summary_filename)
        
        # Configure os.path.exists mock for this test
        def path_exists_side_effect_for_integrate(path):
            if path == expected_combined_summary_path: return True # This is the crucial check
            if path == self.tab.markdown_directory: return True # For get_markdown_files()
            if path == self.tab.results_output_directory: return True # General existence
            return False
        self.mock_path_exists.side_effect = path_exists_side_effect_for_integrate
        
        # Mock os.listdir for get_markdown_files()
        self.mock_listdir.return_value = ["original1.md"]

        # Mock the QProgressDialog that shows up
        mock_progress_dialog_instance = MagicMock()
        mock_qprogressdialog.return_value = mock_progress_dialog_instance

        mock_thread_instance = MockIntegratedAnalysisThread.return_value 
        self.tab.generate_integrated_analysis()

        MockIntegratedAnalysisThread.assert_called_once_with(
            self.tab, # parent
            expected_combined_summary_path, # This is the key path to verify
            [os.path.join(self.tab.markdown_directory, "original1.md")],
            self.tab.results_output_directory,
            self.tab.subject_input.text(),
            self.tab.dob_input.text(),
            self.tab.case_info_input.toPlainText(),
            self.tab.status_panel,
            mock_progress_dialog_instance, # Check that the mock dialog is passed 
            self.tab.selected_llm_provider_id,
            self.tab.selected_llm_model_name
        )
        mock_thread_instance.start.assert_called_once()

    @patch('os.path.getmtime')
    def test_refresh_file_list_populates_from_root_and_subdir(self, mock_getmtime):
        self.tab.results_output_directory = "/fake/results_dir"
        summaries_full_path = os.path.join(self.tab.results_output_directory, SUMMARIES_SUBDIR)

        def listdir_side_effect(path):
            if path == self.tab.results_output_directory:
                return ["root_file.md", "other_file.txt"]
            elif path == summaries_full_path:
                return ["summary1.md", "summary2.md"]
            return []
        self.mock_listdir.side_effect = listdir_side_effect
        
        def path_exists_side_effect(path):
            return path in [self.tab.results_output_directory, summaries_full_path]
        self.mock_path_exists.side_effect = path_exists_side_effect

        mock_getmtime.return_value = 0 

        self.tab.file_selector.clear = MagicMock()
        self.tab.file_selector.addItem = MagicMock()

        self.tab.refresh_file_list()

        self.tab.file_selector.clear.assert_called_once()
        
        expected_items = [
            ("Select a file to preview", None),
            ("root_file.md", os.path.join(self.tab.results_output_directory, "root_file.md")),
            (os.path.join(SUMMARIES_SUBDIR, "summary1.md"), os.path.join(summaries_full_path, "summary1.md")),
            (os.path.join(SUMMARIES_SUBDIR, "summary2.md"), os.path.join(summaries_full_path, "summary2.md")),
        ]
        
        actual_calls = self.tab.file_selector.addItem.call_args_list
        
        self.assertEqual(actual_calls[0], call(expected_items[0][0], expected_items[0][1]))

        actual_items_added = set()
        for acall in actual_calls[1:]: 
             actual_items_added.add((acall[0][0], acall[0][1]))
        
        expected_items_to_find = set()
        for item_text, item_data in expected_items[1:]: 
            expected_items_to_find.add((item_text, item_data))

        self.assertEqual(actual_items_added, expected_items_to_find)


if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False) 
