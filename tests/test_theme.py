from app.theme import APP_STYLE


class TestAppStyle:
    def test_style_is_nonempty(self):
        assert isinstance(APP_STYLE, str)
        assert len(APP_STYLE) > 0

    def test_contains_selectors(self):
        assert "QMainWindow" in APP_STYLE
        assert "QPushButton" in APP_STYLE
        assert "QToolBar" in APP_STYLE

    def test_applies_without_error(self, qapp):
        qapp.setStyleSheet(APP_STYLE)
        # If we get here without an exception, the stylesheet is valid
        assert qapp.styleSheet() == APP_STYLE
