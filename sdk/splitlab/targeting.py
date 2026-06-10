def evaluate_targeting(rules: dict | None, attributes: dict[str, str]) -> bool:
    if rules is None:
        return True
    return _evaluate_node(rules, attributes)


def _evaluate_node(node: dict, attributes: dict[str, str]) -> bool:
    if "operator" in node:
        op = node["operator"]
        sub_rules = node.get("rules", [])
        if op == "AND":
            return all(_evaluate_node(r, attributes) for r in sub_rules)
        elif op == "OR":
            return any(_evaluate_node(r, attributes) for r in sub_rules)
        return False
    if "key" in node:
        return _evaluate_condition(node, attributes)
    return False


def _evaluate_condition(cond: dict, attributes: dict[str, str]) -> bool:
    key = cond.get("key")
    op = cond.get("op")

    if key not in attributes:
        return False

    attr_value = attributes[key]

    if op == "eq":
        return attr_value == cond.get("value")
    elif op == "neq":
        return attr_value != cond.get("value")
    elif op == "in":
        return attr_value in (cond.get("values") or [])
    elif op == "not_in":
        return attr_value not in (cond.get("values") or [])
    elif op == "contains":
        return (cond.get("value") or "") in attr_value
    elif op in ("gt", "lt", "gte", "lte"):
        try:
            a = float(attr_value)
            b = float(cond.get("value", "0"))
        except (ValueError, TypeError):
            return False
        if op == "gt":
            return a > b
        elif op == "lt":
            return a < b
        elif op == "gte":
            return a >= b
        elif op == "lte":
            return a <= b
    return False
