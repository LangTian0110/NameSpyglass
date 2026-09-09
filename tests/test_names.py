from spyglass.names import load_names, validate_name


def test_validate_name():
    assert validate_name("abc") is None
    assert validate_name("Notch_01") is None
    assert validate_name("a" * 16) is None
    assert validate_name("ab") is not None  # 太短
    assert validate_name("a" * 17) is not None  # 太长
    assert validate_name("bad name") is not None  # 含空格
    assert validate_name("名字") is not None  # 非字母数字
    assert validate_name("") is not None


def test_load_names_dedupe_and_skip(tmp_path):
    f = tmp_path / "names.txt"
    f.write_text(
        "# 注释\n"
        "Notch\n"
        "notch\n"
        "\n"
        "ok_name\n"
        "ab\n"
        "名字\n",
        encoding="utf-8",
    )
    names, skipped = load_names(str(f))
    assert names == ["Notch", "ok_name"]  # 大小写不敏感去重，保留首见写法
    assert len(skipped) == 3  # ab / 名字 / 重复
    assert any("重复" in s for s in skipped)
