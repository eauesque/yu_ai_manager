"""Extensions service layer.

Pure-async handlers that get registered onto the Quart blueprint defined in
``routes/extensions_api/routes.py``. Validation / DB / lifecycle calls live
here; routes.py only does URL → handler wiring.
"""
