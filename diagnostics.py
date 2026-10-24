"""Persistent diagnostics for GUI launches (pythonw has no visible stderr)."""
import faulthandler
import logging
from pathlib import Path
import sys
import tempfile

_fatal_log=None


def install(root,folder):
    global _fatal_log
    try:
        directory=Path(folder)/'logs'; directory.mkdir(exist_ok=True)
        _fatal_log=(directory/'crash.log').open('a',encoding='utf-8')
    except OSError:
        directory=Path(tempfile.gettempdir())/'Projectunio-logs'; directory.mkdir(exist_ok=True)
        _fatal_log=(directory/'crash.log').open('a',encoding='utf-8')
    logging.basicConfig(filename=directory/'projectunio.log',encoding='utf-8',level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    faulthandler.enable(_fatal_log,all_threads=True)
    def report(kind,error,tb):
        logging.error('Erreur de l’application',exc_info=(kind,error,tb))
        from tkinter import messagebox
        messagebox.showerror('Projectunio',f'Une erreur est survenue : {error}\n\nLe détail a été enregistré dans :\n{directory}',parent=root)
    root.report_callback_exception=report
    sys.excepthook=report
    logging.info('Démarrage Projectunio — Python %s',sys.version)
