import gc
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import app


class IconToolbarTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk(); self.a=app.App(self.root); self.root.update()

    def tearDown(self):
        self.root.destroy()
        for worker in (self.a.timeline_tools.worker,self.a.still_renderer.worker,self.a.live_audio.worker,self.a.media_work.worker):worker.join(5)
        gc.collect()

    def test_toolbar_fits_and_all_buttons_have_images_and_tooltips(self):
        bar=self.a.icon_toolbar
        self.assertNotIn('loupe',bar.buttons)
        self.assertEqual(len(bar.tooltips),len(bar.buttons))
        for name,button in bar.buttons.items():
            self.assertTrue(button.cget('image')); self.assertTrue(button.cget('text')); self.assertLessEqual(button.winfo_x()+button.winfo_width(),bar.winfo_width())
        self.root.geometry('1080x780'); self.root.update()
        for button in bar.buttons.values():self.assertLessEqual(button.winfo_x()+button.winfo_width(),bar.winfo_width())

    def test_draw_right_click_cancels_partial_and_empty_drawing(self):
        a=self.a; bar=a.icon_toolbar
        for partial in (False,True):
            count=len(a.data['zones']); bar.buttons['draw'].invoke(); self.assertEqual(a.edit_mode.get(),'draw')
            if partial:
                ox,oy,w,h=a.viewport(a.canvas); a.zone_click(SimpleNamespace(x=ox+.2*w,y=oy+.2*h))
            a.canvas.event_generate('<Button-3>',x=50,y=50); self.root.update()
            self.assertIsNone(a.drawing_zone); self.assertEqual(a.edit_mode.get(),'mapping'); self.assertEqual(len(a.data['zones']),count)
            self.assertFalse(a.canvas.find_withtag('new_zone')); self.assertEqual(a.canvas.cget('cursor'),'')

    def test_mode_grid_and_lock_icons_keep_original_behavior(self):
        a=self.a; buttons=a.icon_toolbar.buttons
        buttons['video'].invoke(); self.assertEqual(a.edit_mode.get(),'video')
        buttons['mapping'].invoke(); self.assertEqual(a.edit_mode.get(),'mapping')
        before=a.mapping_grid.get(); buttons['grid'].invoke(); self.assertNotEqual(a.mapping_grid.get(),before)
        buttons['lock_mapping'].invoke(); self.assertTrue(a.data['locks']['mapping'])
        buttons['draw'].invoke(); self.assertIsNone(a.drawing_zone)
        buttons['lock_mapping'].invoke(); self.assertFalse(a.data['locks']['mapping'])
        count=len(a.documents); buttons['new'].invoke(); self.assertEqual(len(a.documents),count+1)

    def test_hdmi_icons_follow_open_close_switch_and_escape(self):
        a=self.a; buttons=a.icon_toolbar.buttons
        with patch('app.screens',return_value=[(0,0,1280,720),(1280,0,1280,720)]),patch('app.place_projector_window'):
            buttons['mire'].invoke(); self.assertTrue(a.hdmi_vars['mire'].get()); self.assertFalse(a.hdmi_vars['image'].get())
            buttons['image'].invoke(); self.assertFalse(a.hdmi_vars['mire'].get()); self.assertTrue(a.hdmi_vars['image'].get())
            a.output.destroy(); self.assertFalse(a.hdmi_vars['image'].get())
            buttons['image'].invoke(); buttons['image'].invoke(); self.assertIsNone(a.output); self.assertFalse(a.hdmi_vars['image'].get())

    def test_tooltip_has_readable_name_and_closes_on_click(self):
        tip=self.a.icon_toolbar.tooltips[0]; tip.show(); self.root.update()
        self.assertTrue(tip.window.winfo_exists()); self.assertIn('Nouveau projet',tip.text)
        tip.widget.event_generate('<ButtonPress-1>'); self.assertIsNone(tip.window)


if __name__=='__main__':unittest.main()
