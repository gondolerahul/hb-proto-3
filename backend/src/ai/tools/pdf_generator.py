"""
PDF Generator Tool for HireBuddha AI Platform.

Generates professional PDF documents from markdown or HTML content using WeasyPrint.
Supports tables, lists, code blocks, and proper formatting with citations.
"""

import json
import os
import tempfile
from typing import Dict, Any
from datetime import datetime
from pathlib import Path
from src.ai.tools.base import Tool

try:
    from weasyprint import HTML, CSS
    from weasyprint.text.fonts import FontConfiguration
except ImportError:
    HTML = None
    CSS = None
    FontConfiguration = None

try:
    import markdown
except ImportError:
    markdown = None


class PDFGeneratorTool(Tool):
    """Tool for generating professional PDF documents from markdown content.
    
    Features:
        - Converts markdown to PDF with proper formatting
        - Supports headers, lists, tables, code blocks
        - Includes table of contents
        - Professional styling with page numbers
        - Citation and reference formatting
    """
    
    name = "pdf_generator"
    description = (
        "Generate a professional PDF document from markdown content. "
        "Input should be a JSON object with 'content' (markdown text), "
        "'title', and 'filename'. Optional: 'author', 'subject'."
    )
    
    # Base directory for artifacts
    BASE_ARTIFACT_DIR = Path("/home/rahul/workspace/dev-hb-codebase/hb-proto-3/backend/artifact")
    
    def __init__(self):
        """Initialize PDF generator."""
        # We'll create directories dynamically in run()
        pass
    
    async def run(self, input_data: str) -> str:
        """Generate a PDF document from markdown content.
        
        Args:
            input_data: JSON string with content, title, filename, etc.
            
        Returns:
            JSON string with pdf_path and metadata
        """
        try:
            params = json.loads(input_data)
            
            # Validate required parameters
            content = params.get("content")
            title = params.get("title")
            filename = params.get("filename")
            
            if not content:
                return json.dumps({"error": "Missing 'content' parameter"})
            if not title:
                return json.dumps({"error": "Missing 'title' parameter"})
            if not filename:
                return json.dumps({"error": "Missing 'filename' parameter"})
            
            # Optional parameters
            author = params.get("author", "HireBuddha Research Agent")
            subject = params.get("subject", "Research Report")
            company_id = params.get("company_id", "default")
            user_id = params.get("user_id", "default")
            
            # Resolve output directory
            output_dir = self.BASE_ARTIFACT_DIR / str(company_id) / str(user_id)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate PDF
            pdf_path = await self._generate_pdf(
                content=content,
                title=title,
                filename=filename,
                author=author,
                subject=subject,
                output_dir=output_dir
            )
            
            return json.dumps({
                "status": "success",
                "pdf_path": str(pdf_path),
                "filename": pdf_path.name,
                "size_bytes": pdf_path.stat().st_size,
                "created_at": datetime.utcnow().isoformat()
            })
            
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid JSON input: {str(e)}"})
        except Exception as e:
            return json.dumps({"error": f"PDF generation failed: {str(e)}"})
    
    async def _generate_pdf(
        self,
        content: str,
        title: str,
        filename: str,
        author: str,
        subject: str,
        output_dir: Path
    ) -> Path:
        """Generate PDF from markdown content using WeasyPrint.
        
        Args:
            content: Markdown formatted content
            title: Document title
            filename: Output filename (without extension)
            author: Document author
            subject: Document subject
            
        Returns:
            Path to generated PDF file
        """
        if not HTML or not markdown:
            raise ImportError(
                "Required libraries not installed. "
                "Install with: pip install weasyprint markdown"
            )
        
        # Pre-process markdown: convert image paths to file:// URIs so WeasyPrint
        # can locate and embed them. Handles:
        #   - absolute paths: /home/rahul/.../panel_1.png  → file:///home/...
        #   - bare filenames with no path: leave as-is (will be unresolved, no crash)
        import re as _re
        def _fix_img_path(m):
            alt = m.group(1)
            path = m.group(2)
            # If it's already a URL (http/https/file), leave it
            if path.startswith(('http://', 'https://', 'file://')):
                return m.group(0)
            # If it's an absolute filesystem path, convert to file:// URI
            if path.startswith('/'):
                # Ensure the file exists before embedding
                if os.path.exists(path):
                    return f'![{alt}](file://{path})'
                else:
                    print(f"Warning: Comic panel image not found at path: {path}")
                    return m.group(0)  # Keep as-is; image won't render but PDF won't crash
            return m.group(0)
        
        processed_content = _re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', _fix_img_path, content)

        # Convert markdown to HTML
        html_content = markdown.markdown(
            processed_content,
            extensions=[
                'extra',  # Tables, fenced code blocks, etc.
                'codehilite',  # Code syntax highlighting
                'toc',  # Table of contents
                'nl2br',  # Newline to <br>
            ]
        )
        
        # Build complete HTML document with styling
        full_html = self._build_html_document(
            html_content=html_content,
            title=title,
            author=author,
            subject=subject
        )
        
        # Strip .pdf extension if provided by LLM to avoid double extension
        clean_filename = filename
        if clean_filename.lower().endswith(".pdf"):
            clean_filename = clean_filename[:-4]
            
        # Generate PDF
        output_path = output_dir / f"{clean_filename}.pdf"
        
        # Create font configuration
        font_config = FontConfiguration()
        
        # Create CSS for styling
        css = CSS(string=self._get_pdf_styles(), font_config=font_config)
        
        # Generate PDF with WeasyPrint
        HTML(string=full_html).write_pdf(
            output_path,
            stylesheets=[css],
            font_config=font_config
        )
        
        print(f"Generated PDF: {output_path.absolute()}")
        return output_path
    
    def _build_html_document(
        self,
        html_content: str,
        title: str,
        author: str,
        subject: str
    ) -> str:
        """Build complete HTML document with metadata and structure.
        
        Args:
            html_content: Converted markdown HTML
            title: Document title
            author: Document author
            subject: Document subject
            
        Returns:
            Complete HTML document string
        """
        current_date = datetime.utcnow().strftime("%B %d, %Y")
        
        return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="author" content="{author}">
    <meta name="subject" content="{subject}">
    <title>{title}</title>
</head>
<body>
    <div class="cover-page">
        <h1 class="report-title">{title}</h1>
        <p class="report-meta">
            <strong>Author:</strong> {author}<br>
            <strong>Date:</strong> {current_date}<br>
            <strong>Subject:</strong> {subject}
        </p>
    </div>
    
    <div class="page-break"></div>
    
    <div class="content">
        {html_content}
    </div>
    
    <div class="footer">
        <span class="page-number"></span>
    </div>
</body>
</html>
"""
    
    def _get_pdf_styles(self) -> str:
        """Get CSS styles for PDF formatting.
        
        Returns:
            CSS string for professional PDF styling
        """
        return """
@page {
    size: A4;
    margin: 2.5cm 2cm 3cm 2cm;
    
    @bottom-center {
        content: "Page " counter(page) " of " counter(pages);
        font-size: 9pt;
        color: #666;
    }
}

body {
    font-family: 'DejaVu Sans', Arial, sans-serif;
    font-size: 11pt;
    line-height: 1.6;
    color: #333;
}

/* Cover Page */
.cover-page {
    text-align: center;
    padding-top: 8cm;
}

.report-title {
    font-size: 28pt;
    font-weight: bold;
    color: #2c3e50;
    margin-bottom: 2cm;
}

.report-meta {
    font-size: 12pt;
    color: #555;
    line-height: 1.8;
}

/* Page Break */
.page-break {
    page-break-after: always;
}

/* Content Styling */
.content {
    text-align: justify;
}

h1 {
    font-size: 20pt;
    color: #2c3e50;
    margin-top: 1.5em;
    margin-bottom: 0.5em;
    page-break-after: avoid;
}

h2 {
    font-size: 16pt;
    color: #34495e;
    margin-top: 1.2em;
    margin-bottom: 0.4em;
    page-break-after: avoid;
}

h3 {
    font-size: 13pt;
    color: #555;
    margin-top: 1em;
    margin-bottom: 0.3em;
    page-break-after: avoid;
}

p {
    margin-bottom: 0.8em;
    text-align: justify;
}

/* Lists */
ul, ol {
    margin-left: 1.5em;
    margin-bottom: 1em;
}

li {
    margin-bottom: 0.3em;
}

/* Tables */
table {
    width: 100%;
    border-collapse: collapse;
    margin: 1em 0;
    page-break-inside: avoid;
}

th {
    background-color: #3498db;
    color: white;
    padding: 8pt;
    text-align: left;
    font-weight: bold;
}

td {
    border: 1px solid #ddd;
    padding: 6pt;
}

tr:nth-child(even) {
    background-color: #f9f9f9;
}

/* Code Blocks */
code {
    background-color: #f4f4f4;
    padding: 2pt 4pt;
    border-radius: 3pt;
    font-family: 'DejaVu Sans Mono', monospace;
    font-size: 9pt;
}

pre {
    background-color: #f4f4f4;
    padding: 10pt;
    border-left: 3pt solid #3498db;
    overflow-x: auto;
    page-break-inside: avoid;
}

pre code {
    background-color: transparent;
    padding: 0;
}

/* Blockquotes */
blockquote {
    border-left: 3pt solid #3498db;
    padding-left: 1em;
    margin-left: 0;
    font-style: italic;
    color: #555;
}

/* Links */
a {
    color: #3498db;
    text-decoration: none;
}

/* Horizontal Rules */
hr {
    border: none;
    border-top: 1pt solid #ddd;
    margin: 1.5em 0;
}

/* Avoid orphans and widows */
p, li {
    orphans: 3;
    widows: 3;
}

/* Keep headings with following content */
h1, h2, h3, h4, h5, h6 {
    page-break-after: avoid;
}

/* Images — ensure comic panel images render large and centred */
img {
    display: block;
    max-width: 16cm;
    width: 100%;
    height: auto;
    margin: 0.8em auto;
    border: 2pt solid #e0e0e0;
    border-radius: 4pt;
    page-break-inside: avoid;
}

/* Comic panel section styling */
h3 {
    background-color: #f0f7ff;
    padding: 6pt 10pt;
    border-left: 4pt solid #3498db;
    border-radius: 0 4pt 4pt 0;
}
"""
    
    def get_function_schema(self) -> Dict[str, Any]:
        """Return JSON schema for function calling."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Markdown formatted content to convert to PDF"
                    },
                    "title": {
                        "type": "string",
                        "description": "Document title"
                    },
                    "filename": {
                        "type": "string",
                        "description": "Output filename (without .pdf extension)"
                    },
                    "author": {
                        "type": "string",
                        "description": "Author name (optional, defaults to 'HireBuddha Research Agent')"
                    },
                    "subject": {
                        "type": "string",
                        "description": "Document subject (optional, defaults to 'Research Report')"
                    }
                },
                "required": ["content", "title", "filename"]
            }
        }
