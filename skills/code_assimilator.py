import ast
import os


class CodeAssimilator:
    """Extracts AST class and function summaries from Python files."""

    def __init__(self):
        self.version = "1.0.0"

    def assimilate_file(self, file_path: str) -> dict:
        if not os.path.exists(file_path):
            return {"error": f"File not found: {file_path}"}
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code_str = f.read()
            return self.assimilate_code(code_str, source_name=os.path.basename(file_path))
        except Exception as e:
            return {"error": f"Failed to read file {file_path}: {e}"}

    def assimilate_code(self, code_str: str, source_name: str = "dynamic_code") -> dict:
        try:
            tree = ast.parse(code_str)
        except SyntaxError as e:
            return {"error": f"Syntax error in code: {e}"}

        extracted_concepts = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                extracted_concepts.append(
                    {
                        "type": "class",
                        "name": node.name,
                        "docstring": ast.get_docstring(node) or "No docstring provided.",
                        "methods": [
                            n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                        ],
                        "source": source_name,
                        "code_snippet": ast.unparse(node)[:500],
                    }
                )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                extracted_concepts.append(
                    {
                        "type": "function",
                        "name": node.name,
                        "docstring": ast.get_docstring(node) or "No docstring provided.",
                        "args": [arg.arg for arg in node.args.args],
                        "source": source_name,
                        "is_async": isinstance(node, ast.AsyncFunctionDef),
                    }
                )

        return {
            "status": "success",
            "source": source_name,
            "concepts": extracted_concepts,
            "total_extracted": len(extracted_concepts),
        }

    def execute(self, action="assimilate_file", **kwargs):
        if action == "assimilate_file":
            file_path = kwargs.get("file_path")
            return self.assimilate_file(file_path) if file_path else {"error": "Missing 'file_path' argument."}
        if action == "assimilate_code":
            code_str = kwargs.get("code_str")
            return self.assimilate_code(code_str) if code_str else {"error": "Missing 'code_str' argument."}
        return {"error": f"Unknown action: {action}"}
