# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------
import os
import sys
import sphinx_rtd_theme # pip3 install sphinx_rtd_theme

# Edit path so all modules can be found
sys.path.insert(0, os.path.abspath('..'))
sys.path.append('/home/vovo/FZU/experimenty/AbloCAM/Xeryon/scripts/')
sys.path.append('../../xeryon_library')

# -- Additional modules ------------------------------------------------------
# `autodoc_mock_imports` includes list of modules used in the project which are
# not included. This list is required for successfull build by readthedocs.
# Including `numpy` into the list generates error message.
# `pypylon` must be included here as it cannot be installed from the
# requirements.txt because it generates some error with wheels.
# Including `Xeryon` in the list is required as long as this library is not
# published within the project.
autodoc_mock_imports = ["pypylon","Xeryon"]

# -- Project information -----------------------------------------------------

project = 'AbloCAM'
copyright = '2021, vovo'
author = 'vovo'

# The full version, including alpha/beta/rc tags
release = '0.1'

# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx_rtd_theme',
    'sphinx.ext.todo',      # Required for boxed todo notes
]

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
# html_theme = 'alabaster'
html_theme = 'sphinx_rtd_theme'     # Use readthedocs theme

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
# html_static_path = ['_static']
html_static_path = []

todo_include_todos = True

# # Load documentation of __init__ method
# def skip(app, what, name, obj, would_skip, options):
#     if name == "__init__":
#         return False
#     return would_skip

# def setup(app):
#     app.connect("autodoc-skip-member", skip)