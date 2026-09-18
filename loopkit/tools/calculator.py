import ast
import math
from typing import Any, Dict

SAFE_FUNCTIONS = {
    "sqrt": math.sqrt,
    "pow": math.pow,
    "round": round,
    "min": min,
    "max": max,
    "abs": abs,
    "log": math.log,
}

SAFE_CONSTANTS = {
    "pi": math.pi,
    "e": math.e,
    "True": True,
    "False": False,
}

class SafeASTEvaluator(ast.NodeVisitor):
    def visit(self, node: ast.AST) -> Any:
        method = "visit_" + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        return visitor(node)

    def generic_visit(self, node: ast.AST) -> Any:
        raise ValueError(f"Disallowed syntax or operation: '{node.__class__.__name__}' is not permitted.")

    def visit_Expression(self, node: ast.Expression) -> Any:
        return self.visit(node.body)

    def visit_Constant(self, node: ast.Constant) -> Any:
        if isinstance(node.value, (int, float, bool)):
            return node.value
        raise ValueError(f"Disallowed constant type: '{type(node.value).__name__}'")

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        operand = self.visit(node.operand)
        if isinstance(node.op, ast.UAdd):
            return +operand
        elif isinstance(node.op, ast.USub):
            return -operand
        elif isinstance(node.op, ast.Not):
            return not operand
        raise ValueError(f"Disallowed unary operator: '{node.op.__class__.__name__}'")

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        left = self.visit(node.left)
        right = self.visit(node.right)

        if isinstance(node.op, ast.Add):
            return left + right
        elif isinstance(node.op, ast.Sub):
            return left - right
        elif isinstance(node.op, ast.Mult):
            return left * right
        elif isinstance(node.op, ast.Div):
            if right == 0:
                raise ZeroDivisionError("Division by zero")
            return left / right
        elif isinstance(node.op, ast.FloorDiv):
            if right == 0:
                raise ZeroDivisionError("Division by zero")
            return left // right
        elif isinstance(node.op, ast.Mod):
            if right == 0:
                raise ZeroDivisionError("Modulo by zero")
            return left % right
        elif isinstance(node.op, ast.Pow):
            if abs(right) > 10000:
                raise ValueError("Exponent too large (safety threshold is 10000)")
            return left ** right
        raise ValueError(f"Disallowed binary operator: '{node.op.__class__.__name__}'")

    def visit_Compare(self, node: ast.Compare) -> Any:
        left = self.visit(node.left)
        for op, comparator in zip(node.ops, node.comparators):
            right = self.visit(comparator)
            if isinstance(op, ast.Eq):
                res = (left == right)
            elif isinstance(op, ast.NotEq):
                res = (left != right)
            elif isinstance(op, ast.Lt):
                res = (left < right)
            elif isinstance(op, ast.LtE):
                res = (left <= right)
            elif isinstance(op, ast.Gt):
                res = (left > right)
            elif isinstance(op, ast.GtE):
                res = (left >= right)
            else:
                raise ValueError(f"Disallowed comparison operator: '{op.__class__.__name__}'")
            if not res:
                return False
            left = right
        return True

    def visit_BoolOp(self, node: ast.BoolOp) -> Any:
        if isinstance(node.op, ast.And):
            for value in node.values:
                val = self.visit(value)
                if not val:
                    return val
            return val
        elif isinstance(node.op, ast.Or):
            for value in node.values:
                val = self.visit(value)
                if val:
                    return val
            return val
        raise ValueError(f"Disallowed boolean operator: '{node.op.__class__.__name__}'")

    def visit_Call(self, node: ast.Call) -> Any:
        if not isinstance(node.func, ast.Name):
            raise ValueError("Direct function calls only. Method calls and attribute access are forbidden.")
        func_name = node.func.id
        if func_name not in SAFE_FUNCTIONS:
            raise ValueError(f"Function '{func_name}' is not in the safe math allowlist ({', '.join(SAFE_FUNCTIONS.keys())}).")
        if node.keywords:
            raise ValueError("Keyword arguments are not allowed in calculator calls.")
        args = [self.visit(arg) for arg in node.args]
        return SAFE_FUNCTIONS[func_name](*args)

    def visit_Name(self, node: ast.Name) -> Any:
        if node.id in SAFE_CONSTANTS:
            return SAFE_CONSTANTS[node.id]
        raise ValueError(f"Unrecognized identifier '{node.id}'. Variable lookups are forbidden.")


class SafeCalculator:
    """AST-parsed sandboxed calculator for arithmetic and comparison expressions."""

    def evaluate(self, expression: str) -> Dict[str, Any]:
        """Evaluates an arithmetic/math expression safely via AST.
        Returns a dict with 'status': 'ok'|'error', 'result': ..., 'error': ...
        """
        if not expression or not expression.strip():
            return {
                "status": "error",
                "error": "Empty expression provided to calculator.",
                "result": None,
            }

        expr_clean = expression.strip()
        try:
            parsed = ast.parse(expr_clean, mode="eval")
            evaluator = SafeASTEvaluator()
            result = evaluator.visit(parsed)
            # Format cleanly
            if isinstance(result, float):
                # Round clean numbers
                if result.is_integer():
                    result = int(result)
                else:
                    result = round(result, 6)
            return {
                "status": "ok",
                "result": result,
                "error": None,
                "summary": f"Calculated: {expr_clean} = {result}"
            }
        except SyntaxError as se:
            return {
                "status": "error",
                "error": f"Invalid syntax in expression '{expr_clean}': {se.msg}",
                "result": None,
            }
        except (ValueError, ZeroDivisionError) as ve:
            return {
                "status": "error",
                "error": f"Math error in '{expr_clean}': {str(ve)}",
                "result": None,
            }
        except Exception as ex:
            return {
                "status": "error",
                "error": f"Calculator rejected expression '{expr_clean}': {type(ex).__name__}: {str(ex)}",
                "result": None,
            }

def safe_calculate(expression: str) -> Dict[str, Any]:
    return SafeCalculator().evaluate(expression)
