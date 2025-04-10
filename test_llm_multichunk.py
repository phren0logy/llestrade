import logging
import os

from llm_utils import LLMClient
from ui.workers.llm_summary_thread import LLMSummaryThread, chunk_document_with_overlap

# Setup logging
logging.basicConfig(level=logging.DEBUG)

# Create test file and directories
test_dir = os.path.join(os.getcwd(), "test_output")
if not os.path.exists(test_dir):
    os.makedirs(test_dir)

# Create a large test document
test_file = os.path.join(os.getcwd(), "test_large.md")
with open(test_file, "w") as f:
    # Generate a large document (over 30K tokens to trigger chunking)
    f.write("# Large Test Document\n\n")
    for i in range(1, 5000):
        f.write(
            f"## Section {i}\n\nThis is test section {i}. It contains some test content that will be used to test the chunking functionality.\n\n"
        )

summary_file = os.path.join(test_dir, "test_large_summary.md")

# Initialize client
client = LLMClient()
print(f"LLMClient initialized")

# Test chunking
with open(test_file, "r") as f:
    content = f.read()
    print(f"Testing chunking...")
    chunks = chunk_document_with_overlap(content, client, 60000, 1000)
    print(f"Document was split into {len(chunks)} chunks")

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
