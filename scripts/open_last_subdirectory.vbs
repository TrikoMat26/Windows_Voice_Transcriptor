Option Explicit

Dim targetFolderPath
Dim fso
Dim folder
Dim subFolder
Dim newestSubFolder
Dim newestDate

' Configure the target folder path here
' Example: targetFolderPath = "C:\\Users\\John\\Documents"
targetFolderPath = InputBox("Entrez le chemin du dossier cible :", "Chemin du dossier")

If Len(Trim(targetFolderPath)) = 0 Then
    WScript.Echo "Aucun chemin fourni. Script interrompu."
    WScript.Quit 1
End If

Set fso = CreateObject("Scripting.FileSystemObject")

If Not fso.FolderExists(targetFolderPath) Then
    WScript.Echo "Le dossier spécifié n'existe pas : " & targetFolderPath
    WScript.Quit 1
End If

Set folder = fso.GetFolder(targetFolderPath)
newestDate = CDate("1900-01-01")
Set newestSubFolder = Nothing

For Each subFolder In folder.SubFolders
    If subFolder.DateCreated > newestDate Then
        Set newestSubFolder = subFolder
        newestDate = subFolder.DateCreated
    End If
Next

If newestSubFolder Is Nothing Then
    WScript.Echo "Aucun sous-dossier trouvé dans : " & targetFolderPath
    WScript.Quit 0
End If

Dim shell
Set shell = CreateObject("WScript.Shell")
shell.Run "explorer.exe """ & newestSubFolder.Path & """", 1, False

WScript.Echo "Dernier sous-dossier ouvert : " & newestSubFolder.Path

