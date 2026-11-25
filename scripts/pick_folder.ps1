# Opens a standard Windows folder picker and prints the chosen path (empty if cancelled).
# Used by launcher 09 so the user selects the project folder instead of typing a path.
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = "Выбери папку проекта для ролика"
$dialog.ShowNewFolderButton = $false
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
    Write-Output $dialog.SelectedPath
}
