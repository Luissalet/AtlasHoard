def test_fixture_case(services, case):
    assert case["r1"]["status"] == "corroborated"
    assert case["r2"]["status"] == "claimed"
