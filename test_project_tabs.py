import json
from pathlib import Path
import tempfile
from unittest.mock import patch
from test_editor_controls import EditorControlsTests


class ProjectTabsTests(EditorControlsTests):
    def test_default_numbering_and_live_custom_name(self):
        self.assertEqual(self.a.name.get(),'Installation 1')
        self.a.new_document(); self.assertEqual(self.a.name.get(),'Installation 2')
        self.a.name.set('Façade'); self.assertEqual(self.a.tabs.tab(self.a.active_document['tab'],'text'),'Façade')
        self.a.new_document(); self.assertEqual(self.a.name.get(),'Installation 3')

    def test_cancel_and_cancel_save_keep_tab(self):
        old=self.a.active_document
        with patch('studio.messagebox.askyesnocancel',return_value=None):self.assertFalse(self.a.close_document())
        self.assertIs(self.a.active_document,old)
        with patch('studio.messagebox.askyesnocancel',return_value=True),patch('app.filedialog.asksaveasfilename',return_value=''):
            self.assertFalse(self.a.close_document())
        self.assertEqual(len(self.a.documents),1)

    def test_discard_last_tab_creates_next_number(self):
        old=self.a.active_document
        with patch('studio.messagebox.askyesnocancel',return_value=False),patch.object(self.a,'save') as save:
            self.assertTrue(self.a.close_document()); save.assert_not_called()
        self.assertNotIn(old,self.a.documents); self.assertEqual(self.a.name.get(),'Installation 2')
        self.assertEqual(len(self.a.documents),1)

    def test_save_before_close_writes_selected_project(self):
        first=self.a.active_document; self.a.name.set('À conserver'); self.a.new_document(); second=self.a.active_document
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'saved.json'
            with patch('studio.messagebox.askyesnocancel',return_value=True),patch('app.filedialog.asksaveasfilename',return_value=str(path)):
                self.assertTrue(self.a.close_document(str(first['tab'])))
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['name'],'À conserver')
        self.assertIs(self.a.active_document,second); self.assertEqual(self.a.name.get(),'Installation 2')

    def test_native_cross_click_cancels_without_selecting_other_tab(self):
        first=self.a.active_document; self.a.new_document(); current=self.a.active_document; self.root.update()
        notebook=self.a.tabs; position=None
        for x in range(notebook.winfo_width()):
            if notebook.identify(x,10)=='ProjectTab.close' and notebook.index(f'@{x},10')==0:position=x; break
        self.assertIsNotNone(position)
        with patch('studio.messagebox.askyesnocancel',return_value=None) as question:
            notebook.event_generate('<ButtonPress-1>',x=position,y=10)
            notebook.event_generate('<ButtonRelease-1>',x=position,y=10)
            self.root.update(); question.assert_called_once()
        self.assertIs(self.a.active_document,current); self.assertIn(first,self.a.documents)
