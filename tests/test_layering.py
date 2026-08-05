from tools.check_layering import check

def test_gui_boundary_does_not_import_kstock() -> None:
    assert check() == []
