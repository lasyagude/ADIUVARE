from adiuvare.vendor._libinjection import detect_sqli, detect_xss, normalize


def test_normalize_decodes_common_wrapper_noise():
    text = "%3Cscript%3Ealert%281%29%3C%2Fscript%3E"
    assert normalize(text) == "<script>alert(1)</script>"


def test_detect_sqli_falls_back_when_dll_is_missing():
    res = detect_sqli("' or 1=1 --")
    assert res["hit"] is True
    assert res["conf"] > 0.0


def test_detect_xss_falls_back_when_dll_is_missing():
    res = detect_xss("<script>alert(1)</script>")
    assert res["hit"] is True
    assert res["conf"] > 0.0
