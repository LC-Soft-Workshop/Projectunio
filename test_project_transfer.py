import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from project_transfer import gather_project,check_resources,check_media


class TransferTests(unittest.TestCase):
    def test_transfer_survives_move_with_duplicate_names_and_occurrences(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name,value in [('a',b'first'),('b',b'second')]:
                (root/name).mkdir(); (root/name/'été.mp4').write_bytes(value)
            data=dict(resolution=[1280,720],clips=[dict(path=str(root/'a'/'été.mp4')),dict(path=str(root/'b'/'été.mp4'))],audio_clips=[dict(path=str(root/'a'/'été.mp4'))])
            before=copy.deepcopy(data); project=gather_project(data,root/'copie')
            (root/'copie').rename(root/'déplacé')
            saved=json.loads((root/'déplacé'/project.name).read_text(encoding='utf-8'))
            paths=[root/'déplacé'/c['path'] for c in saved['clips']]
            self.assertEqual([p.read_bytes() for p in paths],[b'first',b'second'])
            self.assertEqual(saved['audio_clips'][0]['path'],saved['clips'][0]['path'])
            self.assertEqual(len(list((root/'déplacé'/'medias').iterdir())),2)
            self.assertEqual(data,before)

    def test_missing_media_and_copy_failure_publish_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/'source'; source.write_bytes(b'x')
            with self.assertRaises(ValueError):gather_project(dict(clips=[dict(path=str(root/'missing'))]),root/'missing-output')
            with patch('project_transfer.shutil.copy2',side_effect=OSError('copy failed')):
                with self.assertRaises(OSError):gather_project(dict(clips=[dict(path=str(source))]),root/'output')
            self.assertFalse((root/'output').exists())
            self.assertEqual(sorted(p.name for p in root.iterdir()),['source'])
            with self.assertRaises(ValueError):gather_project({},root)

    def test_disk_budget_and_source_overwrite_are_rejected(self):
        data=dict(resolution=[1280,720],clips=[],audio_clips=[])
        with patch('project_transfer.shutil.disk_usage',return_value=SimpleNamespace(free=0)):
            with self.assertRaisesRegex(ValueError,'temporaire'):check_resources(data)
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.mp4'; source.write_bytes(b'original')
            data['clips']=[dict(path=str(source),start=0.,**{'in':0.,'out':1.})]
            with self.assertRaisesRegex(ValueError,'source'):check_resources(data,source)
            self.assertEqual(source.read_bytes(),b'original')

    def test_changed_media_duration_or_audio_is_rejected(self):
        from test_studio import clip
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.mp4'; source.write_bytes(b'x')
            data=dict(clips=[clip(source,audio=True)],audio_clips=[])
            with patch('project_transfer.montage.probe',return_value=(1.,True)):
                with self.assertRaisesRegex(ValueError,'court'):check_media(data,'ffmpeg')
            with patch('project_transfer.montage.probe',return_value=(3.,False)):
                with self.assertRaisesRegex(ValueError,'Son'):check_media(data,'ffmpeg')

    def test_failed_preflight_keeps_existing_export(self):
        import queue
        import app
        from render_job import RenderJob
        from test_studio import clip
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); target=root/'final.mp4'; target.write_bytes(b'previous export')
            events=queue.Queue()
            job=RenderJob(events,app.ffmpeg(),app.DEFAULT['zones'],[clip(root/'missing.mp4')],[],'test',app.mask,app.graph,app.write_mire,app.output_options,destination=target)
            job.thread.start(); job.thread.join(5)
            self.assertFalse(job.thread.is_alive()); self.assertIsNone(job.proc)
            self.assertEqual(target.read_bytes(),b'previous export')
            results=[]
            while not events.empty():results.append(events.get())
            self.assertTrue(any(kind=='error' and 'introuvable' in str(value) for _,kind,value in results))


if __name__=='__main__':unittest.main()
