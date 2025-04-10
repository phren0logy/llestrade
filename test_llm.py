import logging
import os

from llm_utils import LLMClient
from ui.workers.llm_summary_thread import LLMSummaryThread

# Setup logging
logging.basicConfig(level=logging.DEBUG)

# Create test file and directories
test_dir = os.path.join(os.getcwd(), "test_output")
if not os.path.exists(test_dir):
    os.makedirs(test_dir)

test_file = os.path.join(os.getcwd(), "test_markdown.md")
summary_file = os.path.join(test_dir, "test_summary.md")

# Initialize client
client = LLMClient()
print(f"LLMClient initialized")

# Initialize summary thread
summary_thread = LLMSummaryThread(
    markdown_files=[test_file],
    output_dir=test_dir,
    subject_name="Test Subject",
    subject_dob="2000-01-01",
    case_info="Test case",
)
print(f"LLMSummaryThread initialized")

# Test summarize method
try:
    print(f"Starting summarization of {test_file}")
    summary_path = summary_thread.summarize_markdown_file(test_file, summary_file)
    print(f"Summarization completed: {summary_path}")
except Exception as e:
    print(f"ERROR: {str(e)}")
