import ctypes
from ctypes.wintypes import RECT
from unittest.mock import patch
from test_editor_controls import EditorControlsTests
from display_geometry import monitor_rectangles, place_projector_window
import tkinter as tk


class DisplayGeometryTests(EditorControlsTests):
    def test_hdmi_buttons_toggle_and_switch_modes(self):
        with patch('app.screens',return_value=[(0,0,1280,720),(1280,0,1280,720)]),patch('app.place_projector_window'):
            for mode in (False,True):
                self.a.projector(mode); output=self.a.output
                self.assertTrue(output.winfo_exists()); self.assertEqual(output.show_frame,mode)
                with patch.object(self.a,'refresh_screens') as refresh:
                    self.a.projector(mode); refresh.assert_not_called()
                self.assertFalse(output.winfo_exists()); self.assertIsNone(self.a.output)
            self.a.projector(False); first=self.a.output
            self.a.projector(True); self.assertFalse(first.winfo_exists()); self.assertTrue(self.a.output.show_frame)
            self.a.output.destroy()  # Closing with Escape must still allow reopening.
            self.a.projector(True); self.assertTrue(self.a.output.winfo_exists())
            self.a.projector(True); self.assertIsNone(self.a.output)

    def test_hdmi_refreshes_stale_resolution_before_placement(self):
        self.a.monitors=[(0,0,1280,720),(1280,0,1600,900)]; self.a.screen.current(0)
        self.a.screen.configure(values=['PC','Projecteur']); self.a.screen.current(1)
        with patch('app.screens',return_value=[(0,0,1280,720),(1280,0,1920,1080)]),patch('app.place_projector_window') as place:
            self.a.projector()
            self.assertEqual(self.a.screen.current(),1)
            self.assertEqual(place.call_args.args[1],(1280,0,1920,1080))
            self.assertIn('1920×1080',self.a.screen.get())
            self.assertIn('1920 × 1080',self.a.status.get())

    def test_native_placement_matches_physical_monitor_rectangle(self):
        monitors=monitor_rectangles(); rectangle=monitors[0]
        window=tk.Toplevel(self.root); window.overrideredirect(True)
        canvas=tk.Canvas(window,highlightthickness=0); canvas.pack(fill='both',expand=True)
        place_projector_window(window,rectangle); self.root.update()
        user=ctypes.windll.user32; hwnd=user.GetAncestor(window.winfo_id(),2)
        user.GetWindowRect.argtypes=[ctypes.c_void_p,ctypes.POINTER(RECT)]
        actual=RECT(); self.assertTrue(user.GetWindowRect(hwnd,ctypes.byref(actual)))
        self.assertEqual((actual.left,actual.top,actual.right-actual.left,actual.bottom-actual.top),rectangle)
        self.assertEqual((canvas.winfo_width(),canvas.winfo_height()),rectangle[2:])
        window.destroy()
