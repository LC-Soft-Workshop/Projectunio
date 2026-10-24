from pathlib import Path
import tempfile
import tkinter as tk
from unittest.mock import patch
from test_editor_controls import EditorControlsTests
import app


class MireGridTests(EditorControlsTests):
    def test_hdmi_grid_independent_from_canvas(self):
        self.a.output=tk.Toplevel(self.root); self.a.output.canvas=tk.Canvas(self.a.output)
        self.a.output.canvas.pack(); self.root.update()
        self.a.mapping_grid.set(False); self.a.mire_grid.set(True); self.a.draw()
        self.assertFalse(self.a.canvas.find_withtag('mapping_grid'))
        self.assertTrue(self.a.output.canvas.find_withtag('mapping_grid'))
        self.a.mire_grid.set(False); self.a.mapping_grid.set(True); self.a.draw()
        self.assertFalse(self.a.output.canvas.find_withtag('mapping_grid'))
        self.assertTrue(self.a.canvas.find_withtag('mapping_grid'))

    def test_usb_grid_can_be_enabled_and_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            zones=[[[.1,.1],[.9,.1],[.9,.9],[.1,.9]]]
            path=Path(tmp)/'mire.ppm'
            app.write_mire(path,zones,101,101,grid=False)
            blank=path.read_bytes().split(b'\n',3)[3]
            app.write_mire(path,zones,101,101,grid=True)
            grid=path.read_bytes().split(b'\n',3)[3]
            center=(50*101+50)*3
            self.assertEqual(blank[center:center+3],b'\0\0\0')
            self.assertNotEqual(grid[center:center+3],b'\0\0\0')
            self.assertGreater(sum(bool(v) for v in grid),sum(bool(v) for v in blank))

    def test_usb_export_captures_option_and_signature(self):
        with patch('app.filedialog.asksaveasfilename',return_value='unused.mp4'),patch('app.RenderJob') as job:
            self.a.mire_grid.set(False); signature=self.a.render_signature(mire=True)
            self.a.export(mire=True)
            writer=job.call_args.args[8]
            self.assertFalse(writer.keywords['grid'])
            self.a.mire_grid.set(True)
            self.assertFalse(writer.keywords['grid'])
            self.assertNotEqual(signature,self.a.render_signature(mire=True))
            self.a.render_jobs.clear(); self.a.active_render=None
