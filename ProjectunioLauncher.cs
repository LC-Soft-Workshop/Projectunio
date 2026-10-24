using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class ProjectunioLauncher
{
    [STAThread]
    private static void Main()
    {
        string folder = AppDomain.CurrentDomain.BaseDirectory;
        string script = Path.Combine(folder, "app.py");
        string python = Path.Combine(folder, "runtime", "python", "pythonw.exe");
        try
        {
            if (!File.Exists(script)) throw new FileNotFoundException("Le fichier app.py est absent. Copiez le dossier Projectunio complet.");
            if (!File.Exists(python)) python = "pythonw.exe";
            ProcessStartInfo start = new ProcessStartInfo(python, "\"" + script + "\"");
            start.WorkingDirectory = folder;
            start.UseShellExecute = false;
            start.CreateNoWindow = true;
            Process.Start(start);
        }
        catch (Exception error)
        {
            MessageBox.Show("Impossible de lancer Projectunio.\n\n" + error.Message,
                "Projectunio", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}
