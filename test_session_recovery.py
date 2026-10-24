import json
import gc
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import tkinter as tk
import unittest
from unittest.mock import patch
import app
from session_recovery import store,interrupted_sessions,process_alive,settings
from studio import atomic_json


class RecoveryStorageTests(unittest.TestCase):
    def test_finished_process_leaves_a_recoverable_interrupted_session(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'session-crash.json'
            command="import sys,os; from session_recovery import store; from studio import atomic_json; store(sys.argv[1],dict(version=1,state='running',dirty=True,projects=[dict(data=dict(name='Travail interrompu'))]),atomic_json); os._exit(17)"
            result=subprocess.run([sys.executable,'-c',command,str(path)],timeout=20)
            self.assertEqual(result.returncode,17); self.assertEqual(interrupted_sessions(folder),[path])

    def test_atomic_history_retention_and_previous_copy_survives_failed_save(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'session-test.json'
            for n in range(12):store(path,dict(version=1,state='running',projects=[n]),atomic_json)
            versions=list((path.parent/'history'/path.stem).glob('*.json'))
            self.assertEqual(len(versions),10); self.assertEqual(json.loads(path.read_text())['projects'],[11])
            with patch('studio.os.replace',side_effect=OSError('disk unavailable')):
                with self.assertRaises(OSError):store(path,dict(projects=[99]),atomic_json)
            self.assertEqual(json.loads(path.read_text())['projects'],[11])

    def test_interrupted_detection_excludes_clean_live_and_untouched_sessions(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name,state,pid,dirty in [('crash','running',98765,True),('closed','closed',98765,True),('live','running',os.getpid(),True),('empty','running',98765,False)]:
                atomic_json(root/f'session-{name}.json',dict(state=state,pid=pid,dirty=dirty,projects=[{}]))
            (root/'session-corrupt.json').write_text('{')
            with patch('session_recovery.process_alive',side_effect=lambda pid:pid==os.getpid()):
                self.assertEqual([p.name for p in interrupted_sessions(root)],['session-crash.json'])
            self.assertTrue(process_alive(os.getpid()))
            self.assertEqual(settings(root),dict(enabled=True,interval=15))
            atomic_json(root/'settings.json',dict(enabled=False,interval=60)); self.assertEqual(settings(root)['interval'],60)


class RecoveryUITests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk(); self.a=app.App(self.root); self.root.update()
        self.temp=tempfile.TemporaryDirectory(); self.a.recovery_path=Path(self.temp.name)/'session-test.json'

    def tearDown(self):
        self.root.destroy()
        for worker in (self.a.timeline_tools.worker,self.a.still_renderer.worker,self.a.live_audio.worker,self.a.media_work.worker):worker.join(5)
        self.temp.cleanup()
        gc.collect()

    def test_plus_creates_project_and_remains_after_last_tab(self):
        a=self.a; count=len(a.documents); a.tabs.add_button.invoke(); self.root.update()
        self.assertEqual(len(a.documents),count+1); self.assertEqual(a.name.get(),'Installation 2')
        button=a.tabs.add_button; self.assertTrue(button.winfo_ismapped())
        last=0
        for x in range(a.tabs.winfo_width()):
            try:a.tabs.index(f'@{x},10'); last=x+1
            except tk.TclError:pass
        self.assertGreaterEqual(button.winfo_x(),last)
        a.name.set('Un projet avec un nom plus long'); self.root.update(); self.assertGreater(button.winfo_x(),0)

    def test_autosave_and_restore_preserve_open_projects_and_original_file(self):
        a=self.a; original=Path(self.temp.name)/'original.json'; a.save(original); before=original.read_bytes()
        a.name.set('Après modification'); a.new_document(); a.name.set('Projet sans fichier'); a.playhead=0.; a.write_recovery()
        payload=json.loads(a.recovery_path.read_text(encoding='utf-8')); self.assertTrue(payload['dirty']); self.assertEqual(payload['state'],'running')
        count=len(a.documents); a.recover_session(a.recovery_path)
        self.assertEqual(len(a.documents),count+2); self.assertEqual(a.name.get(),'Projet sans fichier'); self.assertEqual(original.read_bytes(),before)
        self.assertEqual(json.loads(a.recovery_path.read_text())['state'],'recovered')
        a.write_recovery(state='closed'); self.assertEqual(json.loads(a.recovery_path.read_text())['state'],'closed')

    def test_autosave_disabled_and_io_failure_are_non_destructive(self):
        a=self.a; self.root.after_cancel(a.autosave_timer); a.recovery_settings['enabled']=False
        with patch.object(a,'write_recovery') as write:a.autosave(); write.assert_not_called()
        self.root.after_cancel(a.autosave_timer); a.recovery_settings['enabled']=True
        with patch.object(a,'write_recovery',side_effect=OSError('disque plein')):a.autosave()
        self.assertIn('impossible',a.status.get()); self.assertTrue(a.autosave_timer)

    def test_manager_lists_versions_and_restores_selected_snapshot(self):
        from tkinter import ttk
        a=self.a; a.name.set('Avant'); a.write_recovery(); a.name.set('Après'); a.write_recovery(); count=len(a.documents)
        a.recovery_manager(); self.root.update()
        win=next(w for w in self.root.winfo_children() if isinstance(w,tk.Toplevel) and w.title()=='Sauvegardes automatiques')
        widgets=[c for parent in win.winfo_children() for c in parent.winfo_children()]
        tree=next(c for c in widgets if isinstance(c,ttk.Treeview)); self.assertGreaterEqual(len(tree.get_children()),3)
        tree.selection_set(tree.get_children()[0])
        next(c for c in widgets if isinstance(c,ttk.Button) and c.cget('text')=='Récupérer la sélection').invoke()
        self.assertEqual(len(a.documents),count+1); win.destroy()


class StartupRecoveryTests(unittest.TestCase):
    def test_startup_banner_restores_interrupted_session(self):
        import copy
        with tempfile.TemporaryDirectory() as folder:
            data=copy.deepcopy(app.DEFAULT); data['name']='Projet retrouvé'
            path=Path(folder)/'session-crash.json'
            atomic_json(path,dict(version=1,state='running',dirty=True,pid=98765,active=0,projects=[dict(data=data,project=None,playhead=0.)]))
            root=tk.Tk()
            with patch.dict(os.environ,PROJECTUNIO_RECOVERY_DIR=folder),patch('session_recovery.process_alive',return_value=False):a=app.App(root)
            try:
                root.update(); self.assertTrue(a.recovery_notice.winfo_ismapped())
                from tkinter import ttk
                button=next(w for w in a.recovery_notice.winfo_children() if isinstance(w,ttk.Button) and w.cget('text')=='Récupérer')
                button.invoke(); self.assertEqual(a.name.get(),'Projet retrouvé'); self.assertEqual(len(a.documents),2)
                self.assertFalse(a.recovery_notice.winfo_exists())
            finally:
                root.destroy()
                for worker in (a.timeline_tools.worker,a.still_renderer.worker,a.live_audio.worker,a.media_work.worker):worker.join(5)
                gc.collect()


if __name__=='__main__':unittest.main()
