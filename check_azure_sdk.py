#!/usr/bin/env python
"""
Check Azure Document Intelligence SDK parameter structure.
"""

import inspect
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest

# Print SDK version
import azure.ai.documentintelligence
print(f"Azure Document Intelligence SDK Version: {azure.ai.documentintelligence.__version__}")

# Check AnalyzeDocumentRequest parameters
print("\nAnalyzeDocumentRequest parameters:")
print(inspect.signature(AnalyzeDocumentRequest.__init__))
print("\nClass docstring:")
print(AnalyzeDocumentRequest.__doc__)

# Check document_intelligence_client.begin_analyze_document
client_class = DocumentIntelligenceClient
print("\nDocumentIntelligenceClient.begin_analyze_document parameters:")
print(inspect.signature(client_class.begin_analyze_document))
print("\nMethod docstring:")
print(client_class.begin_analyze_document.__doc__)
