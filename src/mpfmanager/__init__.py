"""mpf-manager Manages the project level solutions for MPF"""

__version__ = "0.1.0"

def main() -> None:
    from mpfmanager.app import main as app_main

    app_main()