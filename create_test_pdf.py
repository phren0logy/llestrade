#!/usr/bin/env python
"""
Create a simple PDF file for testing.
"""

from fpdf import FPDF

def create_test_pdf(output_path):
    """Create a simple PDF file for testing purposes."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    # Add title
    pdf.set_font("Arial", "B", 16)
    pdf.cell(200, 10, "Test PDF Document", ln=True, align="C")
    
    # Add content
    pdf.set_font("Arial", size=12)
    pdf.ln(10)
    pdf.cell(200, 10, "This is a simple test PDF document created for testing Azure Document Intelligence.", ln=True)
    pdf.ln(5)
    pdf.cell(200, 10, "It contains some basic text content to see if Azure can process it correctly.", ln=True)
    pdf.ln(10)
    
    # Add some structured content
    pdf.set_font("Arial", "B", 14)
    pdf.cell(200, 10, "Section 1: Patient Information", ln=True)
    pdf.set_font("Arial", size=12)
    pdf.ln(5)
    pdf.cell(200, 10, "Name: John Doe", ln=True)
    pdf.cell(200, 10, "Date of Birth: 01/15/1980", ln=True)
    pdf.cell(200, 10, "Gender: Male", ln=True)
    pdf.ln(10)
    
    # Add footer
    pdf.set_y(270)
    pdf.set_font("Arial", "I", 8)
    pdf.cell(200, 10, "Test PDF for Azure Document Intelligence Processing", ln=True, align="C")
    
    # Save the PDF
    pdf.output(output_path)
    print(f"Created test PDF: {output_path}")

if __name__ == "__main__":
    output_path = "test_document.pdf"
    create_test_pdf(output_path)
