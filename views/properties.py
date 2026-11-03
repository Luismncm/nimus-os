"""Searchable, editable property lists shared by production and inventory forms."""
import streamlit as st

from services.catalog import clean, saved_values


def property_select(label: str, property_name: str, *, key: str, current: str = '', container=None) -> str:
    options = saved_values(property_name)
    current = clean(current)
    if current:
        # Keep an existing record's spelling when simply opening and saving it.
        options = [value for value in options if value.casefold() != current.casefold()]
        options.append(current)
        options.sort(key=str.casefold)
    selected = (container if container is not None else st).selectbox(
        label, options, index=options.index(current) if current else None,
        key=key, accept_new_options=True,
        placeholder='Selecciona o escribe un valor nuevo',
    )
    value = clean(selected)
    return next((option for option in options if option.casefold() == value.casefold()), value)
