from splitlab.targeting import evaluate_targeting


class TestEvaluateTargetingNone:
    def test_none_rules_returns_true(self):
        assert evaluate_targeting(None, {}) is True
        assert evaluate_targeting(None, {"country": "CN"}) is True


class TestEqOperator:
    def test_eq_match(self):
        rules = {"key": "country", "op": "eq", "value": "CN"}
        assert evaluate_targeting(rules, {"country": "CN"}) is True

    def test_eq_mismatch(self):
        rules = {"key": "country", "op": "eq", "value": "CN"}
        assert evaluate_targeting(rules, {"country": "US"}) is False

    def test_eq_missing_attr(self):
        rules = {"key": "country", "op": "eq", "value": "CN"}
        assert evaluate_targeting(rules, {}) is False


class TestNeqOperator:
    def test_neq_match(self):
        rules = {"key": "country", "op": "neq", "value": "CN"}
        assert evaluate_targeting(rules, {"country": "US"}) is True

    def test_neq_mismatch(self):
        rules = {"key": "country", "op": "neq", "value": "CN"}
        assert evaluate_targeting(rules, {"country": "CN"}) is False

    def test_neq_missing_attr(self):
        rules = {"key": "country", "op": "neq", "value": "CN"}
        assert evaluate_targeting(rules, {}) is False


class TestInOperator:
    def test_in_match(self):
        rules = {"key": "country", "op": "in", "values": ["CN", "US", "JP"]}
        assert evaluate_targeting(rules, {"country": "CN"}) is True

    def test_in_mismatch(self):
        rules = {"key": "country", "op": "in", "values": ["CN", "US", "JP"]}
        assert evaluate_targeting(rules, {"country": "DE"}) is False

    def test_in_empty_values(self):
        rules = {"key": "country", "op": "in", "values": []}
        assert evaluate_targeting(rules, {"country": "CN"}) is False


class TestNotInOperator:
    def test_not_in_match(self):
        rules = {"key": "country", "op": "not_in", "values": ["CN", "US"]}
        assert evaluate_targeting(rules, {"country": "DE"}) is True

    def test_not_in_mismatch(self):
        rules = {"key": "country", "op": "not_in", "values": ["CN", "US"]}
        assert evaluate_targeting(rules, {"country": "CN"}) is False


class TestContainsOperator:
    def test_contains_match(self):
        rules = {"key": "email", "op": "contains", "value": "@example.com"}
        assert evaluate_targeting(rules, {"email": "user@example.com"}) is True

    def test_contains_mismatch(self):
        rules = {"key": "email", "op": "contains", "value": "@example.com"}
        assert evaluate_targeting(rules, {"email": "user@other.com"}) is False


class TestNumericOperators:
    def test_gt_match(self):
        rules = {"key": "age", "op": "gt", "value": "18"}
        assert evaluate_targeting(rules, {"age": "25"}) is True

    def test_gt_mismatch(self):
        rules = {"key": "age", "op": "gt", "value": "18"}
        assert evaluate_targeting(rules, {"age": "16"}) is False

    def test_lt_match(self):
        rules = {"key": "age", "op": "lt", "value": "65"}
        assert evaluate_targeting(rules, {"age": "30"}) is True

    def test_gte_match(self):
        rules = {"key": "score", "op": "gte", "value": "100"}
        assert evaluate_targeting(rules, {"score": "100"}) is True

    def test_gte_mismatch(self):
        rules = {"key": "score", "op": "gte", "value": "100"}
        assert evaluate_targeting(rules, {"score": "99"}) is False

    def test_lte_match(self):
        rules = {"key": "score", "op": "lte", "value": "100"}
        assert evaluate_targeting(rules, {"score": "100"}) is True

    def test_non_numeric_returns_false(self):
        rules = {"key": "age", "op": "gt", "value": "18"}
        assert evaluate_targeting(rules, {"age": "not_a_number"}) is False

    def test_non_numeric_value_returns_false(self):
        rules = {"key": "age", "op": "gt", "value": "abc"}
        assert evaluate_targeting(rules, {"age": "25"}) is False


class TestAndOperator:
    def test_and_all_match(self):
        rules = {
            "operator": "AND",
            "rules": [
                {"key": "country", "op": "in", "values": ["CN", "US"]},
                {"key": "device", "op": "eq", "value": "mobile"},
            ]
        }
        assert evaluate_targeting(rules, {"country": "CN", "device": "mobile"}) is True

    def test_and_one_fails(self):
        rules = {
            "operator": "AND",
            "rules": [
                {"key": "country", "op": "in", "values": ["CN", "US"]},
                {"key": "device", "op": "eq", "value": "mobile"},
            ]
        }
        assert evaluate_targeting(rules, {"country": "CN", "device": "desktop"}) is False

    def test_and_empty_rules(self):
        rules = {"operator": "AND", "rules": []}
        assert evaluate_targeting(rules, {"country": "CN"}) is True


class TestOrOperator:
    def test_or_one_matches(self):
        rules = {
            "operator": "OR",
            "rules": [
                {"key": "country", "op": "eq", "value": "CN"},
                {"key": "country", "op": "eq", "value": "US"},
            ]
        }
        assert evaluate_targeting(rules, {"country": "US"}) is True

    def test_or_none_match(self):
        rules = {
            "operator": "OR",
            "rules": [
                {"key": "country", "op": "eq", "value": "CN"},
                {"key": "country", "op": "eq", "value": "US"},
            ]
        }
        assert evaluate_targeting(rules, {"country": "DE"}) is False

    def test_or_empty_rules(self):
        rules = {"operator": "OR", "rules": []}
        assert evaluate_targeting(rules, {"country": "CN"}) is False


class TestNestedRules:
    def test_three_level_nesting(self):
        rules = {
            "operator": "AND",
            "rules": [
                {"key": "plan", "op": "eq", "value": "premium"},
                {
                    "operator": "OR",
                    "rules": [
                        {
                            "operator": "AND",
                            "rules": [
                                {"key": "country", "op": "eq", "value": "CN"},
                                {"key": "device", "op": "eq", "value": "mobile"},
                            ]
                        },
                        {"key": "country", "op": "eq", "value": "US"},
                    ]
                }
            ]
        }
        assert evaluate_targeting(rules, {"plan": "premium", "country": "CN", "device": "mobile"}) is True
        assert evaluate_targeting(rules, {"plan": "premium", "country": "US"}) is True
        assert evaluate_targeting(rules, {"plan": "free", "country": "CN", "device": "mobile"}) is False


class TestEdgeCases:
    def test_unknown_operator_returns_false(self):
        rules = {"key": "x", "op": "unknown", "value": "y"}
        assert evaluate_targeting(rules, {"x": "y"}) is False

    def test_empty_dict_returns_false(self):
        rules = {}
        assert evaluate_targeting(rules, {"x": "y"}) is False

    def test_missing_key_in_condition(self):
        rules = {"op": "eq", "value": "test"}
        assert evaluate_targeting(rules, {"something": "test"}) is False
