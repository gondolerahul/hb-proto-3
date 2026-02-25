"""File Writer tool for AI Entities."""

import json
import os
from datetime import datetime
from src.ai.tools.base import Tool

class FileWriterTool(Tool):
    """Tool for writing text content to a file."""
    
    name = "file_writer"
    description = (
        "Write text content to a specific file. "
        "Input should be a JSON object with 'filename' and 'content'. "
        "Files are saved in the 'artifacts' directory."
    )
    
    BASE_DIR = "/home/rahul/workspace/dev-hb-codebase/hb-proto-3/backend/artifact"

    async def run(self, input_data: str) -> str:
        try:
            params = json.loads(input_data)
            filename = params.get("filename")
            content = params.get("content")
            
            if not filename or not content:
                return json.dumps({"error": "Missing 'filename' or 'content'"})

            # Ensure safe filename
            filename = os.path.basename(filename)
            if not filename.endswith(('.txt', '.md', '.json', '.csv')):
                filename += ".md"
            
            # Use context injected by worker if available
            company_id = params.get("company_id", "default")
            user_id = params.get("user_id", "default")
            
            output_dir = os.path.join(self.BASE_DIR, str(company_id), str(user_id))
            os.makedirs(output_dir, exist_ok=True)
            
            file_path = os.path.join(output_dir, filename)
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
                
            return json.dumps({
                "status": "success", 
                "file_path": file_path,
                "message": f"Successfully wrote {len(content)} bytes to {filename}"
            })

        except Exception as e:
            return json.dumps({"error": f"File Writer Error: {str(e)}"})

    def get_function_schema(self):
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Name of the file (e.g., notes.md)"},
                    "content": {"type": "string", "description": "Text content to write"}
                },
                "required": ["filename", "content"]
            }
        }
