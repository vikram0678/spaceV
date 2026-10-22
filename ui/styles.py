"""
Sleek Glassmorphic and Modern Dark Theme Stylesheets for PyQt6 UI.
Master Cybernetic Design System for SpaceV.
"""
from config import THEME

MAIN_WINDOW_STYLE = f"""
/* Universal Palette Guard */
QWidget {{
    color: {THEME['text_primary']};
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}}

QWidget#CentralWidget {{
    background-color: {THEME['bg_dark']};
    border: 1px solid {THEME['border_color']};
    border-radius: 16px;
}}

QWidget#HeaderBar {{
    background-color: {THEME['bg_card']};
    border-top-left-radius: 16px;
    border-top-right-radius: 16px;
    border-bottom: 1px solid {THEME['border_color']};
}}

QLabel#AppTitle {{
    color: {THEME['text_primary']};
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}

QLabel#ModelBadge {{
    background-color: rgba(0, 240, 255, 0.08);
    color: {THEME['primary_glow']};
    border: 1px solid rgba(0, 240, 255, 0.3);
    border-radius: 10px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.5px;
    padding: 2px 8px;
}}

QPushButton#HeaderButton, QPushButton#HeaderMinimizeButton, QPushButton#HeaderCloseButton {{
    background: transparent;
    color: {THEME['text_secondary']};
    border: none;
    font-size: 14px;
    font-weight: bold;
    border-radius: 6px;
    padding: 0px;
}}

QPushButton#HeaderMinimizeButton:hover {{
    background-color: #1e293b;
    color: {THEME['primary_glow']};
}}

QPushButton#HeaderCloseButton:hover {{
    background-color: #ef4444;
    color: #ffffff;
}}

/* Toolbar Container */
QWidget#Toolbar {{
    background-color: #0d121d;
    border-bottom: 1px solid {THEME['border_color']};
}}

QPushButton#CursorToggleBtn {{
    background-color: #141c2b;
    color: {THEME['text_secondary']};
    border: 1px solid {THEME['border_color']};
    border-top-left-radius: 6px;
    border-bottom-left-radius: 6px;
    border-top-right-radius: 0px;
    border-bottom-right-radius: 0px;
    border-right: none;
    font-size: 11px;
    font-weight: 600;
    padding: 4px 7px;
}}

QPushButton#CursorToggleBtn:hover {{
    border-color: {THEME['primary_glow']};
    color: {THEME['text_primary']};
}}

QPushButton#CursorToggleBtn[active="true"] {{
    background-color: rgba(0, 240, 255, 0.12);
    color: {THEME['primary_glow']};
    border: 1px solid {THEME['primary_glow']};
    border-right: none;
}}

QPushButton#CursorSpeedArrowBtn {{
    background-color: #141c2b;
    color: {THEME['primary_glow']};
    border: 1px solid {THEME['border_color']};
    border-top-left-radius: 0px;
    border-bottom-left-radius: 0px;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
    font-size: 10px;
    font-weight: bold;
    padding: 4px 5px;
    min-width: 14px;
}}

QPushButton#CursorSpeedArrowBtn:hover {{
    border-color: {THEME['primary_glow']};
    background-color: rgba(0, 240, 255, 0.2);
    color: #ffffff;
}}

QPushButton#CursorSpeedArrowBtn[active="true"] {{
    background-color: rgba(0, 240, 255, 0.12);
    color: {THEME['primary_glow']};
    border: 1px solid {THEME['primary_glow']};
}}

QMenu#CursorSpeedMenu {{
    background-color: {THEME['bg_card']};
    color: {THEME['text_primary']};
    border: 1px solid {THEME['border_color']};
    border-radius: 8px;
    padding: 4px;
    font-size: 11px;
    font-weight: 600;
}}

QMenu#CursorSpeedMenu::item {{
    padding: 5px 14px 5px 20px;
    border-radius: 4px;
}}

QMenu#CursorSpeedMenu::item:selected {{
    background-color: rgba(0, 240, 255, 0.15);
    color: {THEME['primary_glow']};
}}

QPushButton#VoiceToggleBtn {{
    background-color: #141c2b;
    color: {THEME['text_secondary']};
    border: 1px solid {THEME['border_color']};
    border-radius: 6px;
    font-size: 11px;
    font-weight: 600;
    padding: 4px 8px;
}}

QPushButton#VoiceToggleBtn:hover {{
    border-color: #a855f7;
    color: {THEME['text_primary']};
}}

QPushButton#VoiceToggleBtn[active="true"] {{
    background-color: rgba(168, 85, 247, 0.15);
    color: #c084fc;
    border: 1px solid #a855f7;
}}

QPushButton#WakeToggleBtn {{
    background-color: #141c2b;
    color: {THEME['text_secondary']};
    border: 1px solid {THEME['border_color']};
    border-radius: 6px;
    font-size: 11px;
    font-weight: 600;
    padding: 4px 8px;
}}

QPushButton#WakeToggleBtn:hover {{
    border-color: {THEME['accent_green']};
    color: {THEME['text_primary']};
}}

QPushButton#WakeToggleBtn[active="true"] {{
    background-color: rgba(16, 185, 129, 0.15);
    color: #34d399;
    border: 1px solid {THEME['accent_green']};
}}

QPushButton#CompanionToggleBtn {{
    background-color: #141c2b;
    color: {THEME['text_secondary']};
    border: 1px solid {THEME['border_color']};
    border-radius: 6px;
    font-size: 11px;
    font-weight: 600;
    padding: 4px 8px;
}}

QPushButton#CompanionToggleBtn:hover {{
    border-color: #f59e0b;
    color: {THEME['text_primary']};
}}

QPushButton#CompanionToggleBtn[active="true"] {{
    background-color: rgba(245, 158, 11, 0.15);
    color: #fbbf24;
    border: 1px solid #f59e0b;
}}

QPushButton#EmergencyStopBtn {{
    background-color: rgba(239, 68, 68, 0.15);
    color: #f87171;
    border: 1px solid rgba(239, 68, 68, 0.4);
    border-radius: 6px;
    font-size: 11px;
    font-weight: 700;
    padding: 4px 9px;
}}

QPushButton#EmergencyStopBtn:hover {{
    background-color: #ef4444;
    color: #ffffff;
    border-color: #ef4444;
}}

/* Scroll Area & Message Feed - Strictly Transparent */
QScrollArea {{
    background: transparent;
    border: none;
}}

QScrollArea > QWidget {{
    background: transparent;
}}

QScrollArea > QWidget > QWidget {{
    background: transparent;
}}

QWidget#MessagesContainer {{
    background: transparent;
}}

QScrollBar:vertical {{
    border: none;
    background: transparent;
    width: 6px;
    margin: 0px;
}}

QScrollBar::handle:vertical {{
    background: {THEME['border_color']};
    border-radius: 3px;
    min-height: 24px;
}}

QScrollBar::handle:vertical:hover {{
    background: {THEME['primary_glow']};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

/* Quick Action Chips */
QWidget#ChipsContainer {{
    background-color: #0d121c;
    border-top: 1px solid {THEME['border_color']};
    border-bottom: 1px solid {THEME['border_color']};
    padding: 4px 6px;
}}

QPushButton#QuickChipBtn {{
    background-color: #131926;
    color: {THEME['text_secondary']};
    border: 1px solid {THEME['border_color']};
    border-radius: 12px;
    font-size: 11px;
    font-weight: 500;
    padding: 4px 10px;
    white-space: nowrap;
}}

QPushButton#QuickChipBtn:hover {{
    background-color: #1a2336;
    color: {THEME['primary_glow']};
    border-color: rgba(0, 240, 255, 0.4);
}}

QPushButton#QuickChipBtn:pressed {{
    background-color: #0d131f;
}}

QPushButton#DynamicFollowUpChip {{
    background-color: rgba(14, 22, 36, 0.95);
    color: #38bdf8;
    border: 1px solid rgba(56, 189, 248, 0.35);
    border-radius: 10px;
    font-size: 11px;
    font-weight: 600;
    padding: 4px 10px;
}}

QPushButton#DynamicFollowUpChip:hover {{
    background-color: rgba(2, 132, 199, 0.25);
    color: #ffffff;
    border-color: {THEME['primary_glow']};
}}

/* Chat Input Bar */
QWidget#InputContainer {{
    background-color: {THEME['bg_card']};
    border-top: 1px solid {THEME['border_color']};
    border-bottom-left-radius: 16px;
    border-bottom-right-radius: 16px;
    padding: 10px 12px;
}}

QTextEdit#ChatInput {{
    background-color: #0d121c;
    color: {THEME['text_primary']};
    selection-background-color: {THEME['bubble_user']};
    selection-color: #ffffff;
    border: 1px solid {THEME['border_color']};
    border-radius: 10px;
    padding: 10px 12px;
    font-size: 13px;
}}

QTextEdit#ChatInput:focus {{
    border: 1px solid {THEME['primary_glow']};
    background-color: #111724;
}}

QPushButton#MicButton {{
    background-color: #141c2b;
    color: {THEME['text_secondary']};
    border: 1px solid {THEME['border_color']};
    border-radius: 10px;
    font-size: 15px;
    padding: 0px;
    min-width: 44px;
    max-width: 44px;
    height: 44px;
}}

QPushButton#MicButton:hover {{
    border-color: {THEME['primary_glow']};
    color: {THEME['primary_glow']};
    background-color: #1a2336;
}}

QPushButton#MicButton[listening="true"] {{
    background-color: rgba(239, 68, 68, 0.2);
    color: #ef4444;
    border: 1px solid #ef4444;
}}

QPushButton#SendButton {{
    background-color: {THEME['bubble_user']};
    color: #ffffff;
    border: none;
    border-radius: 10px;
    font-size: 13px;
    font-weight: 600;
    padding: 0px 18px;
    height: 44px;
}}

QPushButton#SendButton:hover {{
    background-color: #0369a1;
}}

QPushButton#SendButton:pressed {{
    background-color: #075985;
}}

QPushButton#SendButton:disabled {{
    background-color: #141c2b;
    color: #475569;
}}
"""

def get_user_bubble_style() -> str:
    return f"""
    background-color: {THEME['bubble_user']};
    color: #ffffff;
    border-radius: 14px;
    border-bottom-right-radius: 4px;
    padding: 2px 4px;
    font-size: 13px;
    line-height: 1.45;
    """

def get_agent_bubble_style() -> str:
    return f"""
    background-color: {THEME['bubble_agent']};
    color: {THEME['text_primary']};
    border: 1px solid {THEME['border_color']};
    border-radius: 14px;
    border-bottom-left-radius: 4px;
    padding: 2px 4px;
    font-size: 13px;
    line-height: 1.5;
    """

def get_tool_card_style() -> str:
    return f"""
    background-color: rgba(2, 132, 199, 0.08);
    border: 1px solid rgba(0, 240, 255, 0.3);
    border-radius: 8px;
    color: {THEME['primary_glow']};
    padding: 8px 12px;
    font-size: 11px;
    font-family: 'Consolas', 'Cascadia Code', monospace;
    """

