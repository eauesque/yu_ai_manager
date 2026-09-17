' YU AI Manager - Console-less launcher (Windows)
'
' Double-click this file to run start.bat without showing the cmd window.
' The server will keep running in the background; stop it from the WebUI:
'   Tools tab → Stop Server
' (or use Task Manager to kill node.exe / python.exe if WebUI is unreachable).
'
' First-run note: the launcher's interactive [Y/n] prompts for Node.js and
' ffmpeg auto-install will not be visible when started via this .vbs file.
' To accept everything non-interactively, set the environment variable
'   YU_AUTO_INSTALL=1
' before launching, OR run start.bat once normally to answer the prompts.
'
' Why this waits and writes a log: with a hidden window and no redirection,
' every diagnostic the launcher prints goes nowhere. A database that needs
' migrating (exit 78), a missing interpreter, a port already taken -- all of
' them looked identical from here: nothing happened. The launcher's own
' fallbacks handle most of those, so this matters exactly when they did not,
' which is the moment the operator most needs to be told something.

Const LOG_TAIL_LINES = 20

Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

strScriptDir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))

strArgs = ""
For Each arg In WScript.Arguments
    strArgs = strArgs & " " & Chr(34) & Replace(arg, Chr(34), Chr(34) & Chr(34)) & Chr(34)
Next

' A place to write that is writable even when the install directory is not
' (Program Files). %LOCALAPPDATA% first, %TEMP% as the fallback.
strLog = ""
On Error Resume Next
strBase = objShell.ExpandEnvironmentStrings("%LOCALAPPDATA%")
If strBase <> "" And strBase <> "%LOCALAPPDATA%" Then
    strDir = strBase & "\yu-ai-manager"
    If Not objFSO.FolderExists(strDir) Then objFSO.CreateFolder(strDir)
    If objFSO.FolderExists(strDir) Then strLog = strDir & "\launcher.log"
End If
If strLog = "" Then
    strBase = objShell.ExpandEnvironmentStrings("%TEMP%")
    If strBase <> "" And strBase <> "%TEMP%" Then strLog = strBase & "\yu-launcher.log"
End If
' Prove it is writable before relying on it: a redirect to a path that cannot
' be created would stop the launcher from running at all, which is a far worse
' failure than the silence this replaces.
If strLog <> "" Then
    Set objProbe = objFSO.CreateTextFile(strLog, True)
    If Err.Number <> 0 Then
        strLog = ""
        Err.Clear
    Else
        objProbe.Close
    End If
End If
On Error Goto 0

If strLog = "" Then
    ' No writable log: behave exactly as before rather than not starting.
    objShell.Run """" & strScriptDir & "start.bat""" & strArgs, 0, False
    WScript.Quit 0
End If

' 0 = hide window, True = wait, so the exit code can be reported. The window
' stays hidden either way; waiting costs nothing visible.
strCmd = "cmd /c """"" & strScriptDir & "start.bat""" & strArgs & " > """ & strLog & """ 2>&1"""
rc = objShell.Run(strCmd, 0, True)

If rc <> 0 Then
    strTail = ""
    On Error Resume Next
    Set objLog = objFSO.OpenTextFile(strLog, 1)
    If Err.Number = 0 Then
        Dim arrLines()
        ReDim arrLines(LOG_TAIL_LINES - 1)
        intCount = 0
        Do Until objLog.AtEndOfStream
            arrLines(intCount Mod LOG_TAIL_LINES) = objLog.ReadLine
            intCount = intCount + 1
        Loop
        objLog.Close
        intShown = LOG_TAIL_LINES
        If intCount < intShown Then intShown = intCount
        For i = intCount - intShown To intCount - 1
            strTail = strTail & arrLines(i Mod LOG_TAIL_LINES) & vbCrLf
        Next
    End If
    Err.Clear
    On Error Goto 0

    MsgBox "YU AI Manager could not start (exit code " & rc & ")." & vbCrLf & _
           vbCrLf & "Full log:" & vbCrLf & strLog & vbCrLf & _
           vbCrLf & "Last lines:" & vbCrLf & strTail, _
           vbExclamation, "YU AI Manager"
End If

WScript.Quit rc
