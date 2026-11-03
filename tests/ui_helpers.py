def enter_option(app, key, value):
    """Emulate the frontend's new-option string; AppTest only serializes known options."""
    widget = app.selectbox(key=key)
    if value not in widget.options:
        widget.options.append(value)
    widget.set_value(value)
