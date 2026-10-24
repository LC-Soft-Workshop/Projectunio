import copy
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from test_zone_names import ZoneNameTests
from test_clip_context import video
from studio import validate_extras


class TrackHeaderTests(ZoneNameTests):
    def test_audio_names_and_zero_tracks_save_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'project.json'
            self.t.edit_zone_name(2); self.t.name_edit_value.set('Musique'); self.t.finish_name_edit()
            with patch('app.filedialog.asksaveasfilename',return_value=str(path)):self.a.save()
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['audio_track_names'],['Musique'])
            with patch('app.filedialog.askopenfilename',return_value=str(path)):self.a.load()
            self.assertEqual(self.a.audio_names(),['Musique'])
            self.a.delete_timeline_track(2)
            with patch('app.filedialog.asksaveasfilename',return_value=str(path)):self.a.save()
            with patch('app.filedialog.askopenfilename',return_value=str(path)):self.a.load()
            self.assertEqual(self.t.track_count,0)
            self.t.add_audio_track(); self.assertEqual(self.a.audio_names(),['Audio 1'])

    def test_audio_rename_and_header_menu(self):
        self.t.edit_zone_name(2); self.t.name_edit_value.set('Ambiance'); self.t.finish_name_edit()
        self.assertEqual(self.a.audio_names(),['Ambiance']); validate_extras(self.a.data)
        self.assertEqual(self.a.zone,0)
        event=SimpleNamespace(x=20,y=146,x_root=100,y_root=100)
        with patch('timeline_tools.tk.Menu') as factory:
            self.a.timeline_tools.context_menu(event)
            commands={c.kwargs['label']:c.kwargs['command'] for c in factory.return_value.add_command.call_args_list}
            with patch('studio.messagebox.askyesno') as confirm:commands['Supprimer la piste audio'](); confirm.assert_not_called()
        self.assertEqual(self.t.track_count,0)
        self.a.undo(); self.assertEqual(self.a.audio_names(),['Ambiance'])

    def test_occupied_audio_cancel_delete_reindex_and_undo(self):
        self.t.add_audio_track(); self.t.add_audio_track()
        self.a.data['audio_track_names']=['Musique','Voix','Ambiance']
        self.a.data['audio_clips']=[dict(video(str(i),i),kind='audio') for i in range(3)]
        self.a.data['mixer']={'a0':{'mute':True},'a1':{'solo':True},'a2':{'mute':False},'v1':{'mute':True}}
        before=copy.deepcopy(self.a.data)
        with patch('studio.messagebox.askyesno',return_value=False):self.a.delete_timeline_track(3)
        self.assertEqual(self.a.data,before)
        with patch('studio.messagebox.askyesno',return_value=True) as confirm:self.a.delete_timeline_track(3); confirm.assert_called_once()
        self.assertEqual(self.a.audio_names(),['Musique','Ambiance'])
        self.assertEqual([(c['id'],c['lane']) for c in self.t.audio_clips],[('0',0),('2',1)])
        self.assertEqual(self.a.data['mixer'],{'a0':{'mute':True},'a1':{'mute':False},'v1':{'mute':True}})
        self.a.undo(); self.assertEqual(self.a.data,before)

    def test_occupied_zone_removes_only_target(self):
        self.a.data['clips']=[video('one'),video('two',1)]
        with patch('studio.messagebox.askyesno',return_value=True):self.a.delete_timeline_track(0)
        self.assertEqual(self.a.zone_names(),['Zone 2'])
        self.assertEqual([(c['id'],c['lane']) for c in self.t.clips],[('two',0)])
        self.assertEqual(self.t.track_count,1)
