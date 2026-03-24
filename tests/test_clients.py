# tests/test_dummy.py


def test_always_passes():
    """
    This is a simple dummy test. If pytest runs correctly, this test
    will always pass. It does not import anything from the projectdavid package.
    """
    print("Running test_always_passes...")
    assert True, "This assertion should always succeed."


def test_basic_addition():
    """
    Another simple self-contained test.
    """
    print("Running test_basic_addition...")
    assert 1 + 1 == 2, "Basic math check failed."


# You can add more self-contained tests here if needed.
