# ui/ui_theme.py
# 最簡單、最乾淨、最接近 Streamlit 預設主題

MINIMAL_MAIN_MENU_STYLES = {
    "container": {
        "padding": "0",
        "background-color": "white",
    },
    "icon": {
        "color": "#81A5EC",  
        "font-size": "18px",
    },
    "nav-link": {
        "font-size": "16px",
        "color": "#374151",  # 深灰文字
        "padding": "8px 12px",
        "text-align": "left",
        "margin": "3px 0px",
        "border-radius": "6px",
    },
    "nav-link-selected": {
        "background-color": "#E5E7EB",  # 淺灰（和 Streamlit 控件接近）
        "color": "#111827",
        "font-weight": "500",
    },
}

MINIMAL_SUB_MENU_STYLES = {
    "container": {
        "padding": "0",
        "background-color": "white",
    },
    "icon": {
        "color": "#81A5EC",
        "font-size": "16px",
    },
    "nav-link": {
        "font-size": "14.5px",
        "color": "#4B5563",
        "padding": "6px 12px",
        "margin": "3px 0px",
        "border-radius": "6px",
        "text-align": "left",
    },
    "nav-link-selected": {
        "background-color": "#E5E7EB",  # 更淡的灰
        "color": "#111827",
        "font-weight": "500",
    },
}
