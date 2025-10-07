## Document Content

<document-content>
{document_content}
</document-content>

# Document Analysis Task

## Document Information

- **Subject Name**: {subject_name}
- **Date of Birth**: {subject_dob}
- **Original Document**: (The {document_name} is a markdown file that was converted from a PDF. Change the extension from .md to .pdf)

## Case Background

{case_info}

## Bulk Analysis Instructions

Please analyze the document content, wrapped in "document-content" tags, and provide a comprehensive bulk analysis that includes:

- Key facts and information about the subject
- Significant events and dates mentioned
- Family and romantic relationships
- Early childhood history
- Educational history
- Employment history
- Military career history
- Legal issues or encounters with law enforcement
- Substance use and treatment history
- Medical and psychiatric history
- Any notable statements or quotes
- Notable patterns of behavior
- Adverse life events
- A timeline of events in a markdown table format with columns for Date, Event, and Significance

Include the page number for all extracted items.
Create a markdown link to [filename.pdf: Page x](./pdfs/<filename.pdf>#page=<page_number>) for each page number referenced.
When a range of pages is referenced, link the first page but include the range in the text.

## Timeline Instructions

- Using the subject's date of birth ({subject_dob}), calculate the subject's age at each event when relevant
- Create a timeline of events in a markdown table format with columns for Date, Age, Event, and Significance, and Page Number, where age refer's to the subject's age
- When exact dates aren't provided, estimate years when possible and mark them with "(est.)"
- Organize the timeline chronologically with the most recent events at the bottom
- If there are multiple events on the same date, list them in the order they occurred
- If there are multiple events with the same date and significance, list them in the order they occurred

Keep your analysis focused on factual information directly stated in the document.

Before finalizing results, do a review for accuracy, with attention to exact quotes and markdown links to original PDFs.
