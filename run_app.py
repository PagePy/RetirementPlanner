"""Lanceur de l'application. Usage: python run_app.py [--native]"""
import sys

from gui.main import run_app

if __name__ in {"__main__", "__mp_main__"}:
    run_app(native="--native" in sys.argv)
