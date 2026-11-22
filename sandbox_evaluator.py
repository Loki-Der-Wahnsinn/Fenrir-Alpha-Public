import os
import subprocess
import sys
import tempfile


class SandboxEvaluator:
    """Evaluates generated Python code in an isolated local subprocess."""

    def __init__(self, workspace):
        self.workspace = workspace

    def _evaluate_locally(self, code: str, class_name: str) -> dict:
        tmp_code_path = None
        tmp_runner_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as tf:
                tf.write(code)
                tmp_code_path = tf.name

            runner_script = (
                "import sys, traceback, inspect, importlib.util\n"
                "try:\n"
                f"    spec = importlib.util.spec_from_file_location('sandbox_mod', {tmp_code_path!r})\n"
                "    mod = importlib.util.module_from_spec(spec)\n"
                "    spec.loader.exec_module(mod)\n"
                "    classes = [m for _, m in inspect.getmembers(mod, inspect.isclass) if getattr(m, '__module__', None) == mod.__name__]\n"
                "    functions = [m for _, m in inspect.getmembers(mod, inspect.isfunction) if getattr(m, '__module__', None) == mod.__name__]\n"
                "    if not classes and not functions:\n"
                "        print('ERROR: Kein Code-Objekt gefunden.')\n"
                "        sys.exit(1)\n"
                "    if classes:\n"
                "        try:\n"
                "            classes[0]()\n"
                "        except TypeError:\n"
                "            pass\n"
                "    print('SUCCESS')\n"
                "except Exception as e:\n"
                "    print('ERROR:', str(e))\n"
                "    traceback.print_exc()\n"
                "    sys.exit(1)\n"
            )
            with tempfile.NamedTemporaryFile(mode="w", suffix="_runner.py", delete=False, encoding="utf-8") as rf:
                rf.write(runner_script)
                tmp_runner_path = rf.name

            creationflags = 0x08000000 if sys.platform == "win32" else 0
            env = os.environ.copy()
            ws = os.path.abspath(str(self.workspace))
            env["PYTHONPATH"] = ws + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
            result = subprocess.run(
                [sys.executable, tmp_runner_path],
                cwd=ws,
                env=env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=15,
                creationflags=creationflags,
            )

            if result.returncode == 0 and "SUCCESS" in result.stdout:
                return {
                    "status": "success",
                    "message": "Code passed local sandbox evaluation.",
                    "dopamine_shift": 0.3,
                }
            return {
                "status": "error",
                "message": "Code failed local sandbox evaluation.",
                "stdout": result.stdout,
                "stderr": result.stderr,
                "dopamine_shift": -0.1,
            }
        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "message": "Code evaluation timed out (local sandbox).",
                "dopamine_shift": -0.2,
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Local Sandbox Exception: {str(e)}",
                "dopamine_shift": -0.1,
            }
        finally:
            for p in (tmp_code_path, tmp_runner_path):
                if p and os.path.exists(p):
                    try:
                        os.unlink(p)
                    except OSError:
                        pass

    def evaluate_code(self, code: str, class_name: str) -> dict:
        return self._evaluate_locally(code, class_name)
