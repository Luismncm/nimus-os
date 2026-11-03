from services.recipes import load_catalog
from views.catalog_workspace import render

render(load_catalog())
