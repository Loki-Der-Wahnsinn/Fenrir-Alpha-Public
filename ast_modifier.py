import ast
import os


class SkillMutator(ast.NodeTransformer):
    def __init__(self, target_class: str, method_nodes: list):
        self.target_class = target_class
        self.method_nodes = method_nodes
        self.mutation_successful = False

    def visit_ClassDef(self, node: ast.ClassDef):
        if node.name.strip() == self.target_class.strip():
            existing_methods = [
                n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            for method_node in self.method_nodes:
                if method_node.name in existing_methods:
                    node.body = [
                        n
                        for n in node.body
                        if not (
                            isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                            and n.name == method_node.name
                        )
                    ]
                node.body.append(method_node)
            self.mutation_successful = True
        return node


def apply_mutation(file_path: str, command: dict) -> bool:
    """Applies an AST method addition/update to a Python skill file."""
    if command.get("action") != "add_method":
        return False

    target_class = command.get("class")
    new_code = command.get("code")
    if not target_class or not new_code:
        return False

    if not os.path.exists(file_path):
        os.makedirs(os.path.dirname(file_path) if os.path.dirname(file_path) else ".", exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"class {target_class}:\n    def __init__(self):\n        pass\n")

    with open(file_path, "r", encoding="utf-8") as f:
        source_code = f.read()

    try:
        source_ast = ast.parse(source_code)
        method_ast = ast.parse(new_code)

        imports_to_add = []
        methods_to_add = []
        for n in method_ast.body:
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                imports_to_add.append(n)
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods_to_add.append(n)

        if not methods_to_add:
            return False

        if imports_to_add:
            source_ast.body = imports_to_add + source_ast.body

        mutator = SkillMutator(target_class, methods_to_add)
        modified_ast = mutator.visit(source_ast)
        ast.fix_missing_locations(modified_ast)

        if not mutator.mutation_successful:
            new_class = ast.ClassDef(
                name=target_class.strip(),
                bases=[],
                keywords=[],
                body=methods_to_add,
                decorator_list=[],
            )
            modified_ast.body.append(new_class)
            ast.fix_missing_locations(modified_ast)

        mutated_code = ast.unparse(modified_ast)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(mutated_code)
        return True
    except (SyntaxError, Exception):
        return False
