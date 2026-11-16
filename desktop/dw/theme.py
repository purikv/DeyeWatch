# -*- coding: utf-8 -*-
"""Палітра і стилі. Тема слідує за системою або задається вручну."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication

LIGHT = {
    "bg": "#F6F7F9", "surface": "#FFFFFF", "surface2": "#F0F1F4", "border": "#E3E5EA",
    "text": "#1A1C22", "muted": "#6B6F7B", "faint": "#9A9EA8",
    "accent": "#3E63DD", "ok": "#30A46C", "bad": "#E5484D", "warn": "#F5A524",
    "orange": "#F76B15", "pv": "#F5A524", "load": "#3E63DD", "grid": "#8E4EC6",
    "batt": "#30A46C", "sold": "#12A594", "gen": "#B5651D", "grid_line": "#ECEEF2", "shadow": "#1A1C2214",
    "insight": "#EEF2FD", "insight_b": "#D9E1FA",
}
DARK = {
    "bg": "#111215", "surface": "#191A1F", "surface2": "#212329", "border": "#2B2D35",
    "text": "#EDEEF0", "muted": "#A0A4AE", "faint": "#6B6F7B",
    "accent": "#7090F0", "ok": "#3DD68C", "bad": "#FF6369", "warn": "#FFC53D",
    "orange": "#FF8B3E", "pv": "#FFC53D", "load": "#7090F0", "grid": "#BF7AF0",
    "batt": "#3DD68C", "sold": "#0BD8B6", "gen": "#E0975A", "grid_line": "#23252B", "shadow": "#00000066",
    "insight": "#1B2033", "insight_b": "#28304A",
}

T = dict(LIGHT)


def is_dark(pref):
    if pref == "dark":
        return True
    if pref == "light":
        return False
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return False


def apply(pref):
    T.clear()
    T.update(DARK if is_dark(pref) else LIGHT)
    T["dark"] = is_dark(pref)
    return T


def c(name, alpha=None):
    col = QColor(T[name])
    if alpha is not None:
        col.setAlphaF(alpha)
    return col


def qss():
    return """
    * { font-family: 'Segoe UI Variable Text', 'Segoe UI', 'Inter', 'Cantarell', 'Noto Sans', sans-serif; }
    QWidget#root { background: %(bg)s; }
    QWidget { color: %(text)s; font-size: 13px; }
    QLabel#h1 { font-size: 24px; font-weight: 600; }
    QLabel#h2 { font-size: 15px; font-weight: 600; }
    QLabel#muted { color: %(muted)s; }
    QLabel#hero { font-size: 30px; font-weight: 600; }
    QLabel#heroSub { font-size: 14px; color: %(muted)s; }
    QLabel#value { font-size: 26px; font-weight: 600; }
    QLabel#value2 { font-size: 22px; font-weight: 600; }
    QLabel#body { font-size: 14px; }
    QLabel#brand { font-size: 16px; font-weight: 600; }
    QLabel#faint { color: %(faint)s; font-size: 12px; }
    QLabel#info { color: %(faint)s; border: 1px solid %(faint)s; border-radius: 8px; font-size: 10px; font-weight: 600; }
    QLabel#info:hover { color: %(accent)s; border-color: %(accent)s; }
    QFrame#insight { background: %(insight)s; border: 1px solid %(insight_b)s; border-radius: 12px; }
    QFrame#onboard { background: %(surface)s; border: 1px solid %(accent)s; border-radius: 14px; }
    QLabel#hint { color: %(faint)s; font-size: 11px; }
    QLabel#legend { color: %(muted)s; font-size: 12px; }
    QFrame#card { background: %(surface)s; border: 1px solid %(border)s; border-radius: 14px; }
    QFrame#sidebar { background: %(surface)s; border-right: 1px solid %(border)s; }
    QPushButton#nav { text-align: left; padding: 9px 14px; border: none; border-radius: 9px;
        color: %(muted)s; font-size: 13px; font-weight: 500; background: transparent; }
    QPushButton#nav:hover { background: %(surface2)s; color: %(text)s; }
    QPushButton#nav:checked { background: %(surface2)s; color: %(text)s; font-weight: 600; }
    QPushButton { background: %(surface2)s; border: 1px solid %(border)s; border-radius: 8px;
        padding: 7px 14px; font-weight: 500; }
    QPushButton:hover { border-color: %(faint)s; }
    QPushButton#primary { background: %(accent)s; color: white; border: none; }
    QPushButton#primary:hover { background: %(accent)s; }
    QPushButton#seg { border-radius: 7px; padding: 5px 12px; background: transparent; border: none; color: %(muted)s; }
    QPushButton#seg:checked { background: %(surface)s; color: %(text)s; border: 1px solid %(border)s; }
    QFrame#segbox { background: %(surface2)s; border-radius: 9px; }
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
        background: %(surface)s; border: 1px solid %(border)s; border-radius: 8px; padding: 6px 9px;
        selection-background-color: %(accent)s; min-height: 18px; }
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border: 1px solid %(accent)s; }
    QComboBox::drop-down { border: none; width: 22px; }
    QComboBox QAbstractItemView { background: %(surface)s; border: 1px solid %(border)s; selection-background-color: %(surface2)s; selection-color: %(text)s; }
    QScrollArea { border: none; background: transparent; }
    QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
    QScrollBar::handle:vertical { background: %(border)s; border-radius: 4px; min-height: 30px; }
    QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
    QToolTip { background: %(surface)s; color: %(text)s; border: 1px solid %(border)s; padding: 6px; border-radius: 6px; }
    QTableWidget { background: transparent; border: none; gridline-color: transparent; }
    QHeaderView::section { background: transparent; color: %(faint)s; border: none; padding: 6px 4px; font-size: 12px; text-align: left; }
    QTableWidget::item { padding: 6px 4px; border-bottom: 1px solid %(grid_line)s; }
    """ % T
