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

Set objShell = CreateObject("WScript.Shell")
strScriptDir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
strArgs = ""
For Each arg In WScript.Arguments
    strArgs = strArgs & " " & Chr(34) & Replace(arg, Chr(34), Chr(34) & Chr(34)) & Chr(34)
Next
' 0 = hide window, False = do not wait for the process to finish.
objShell.Run """" & strScriptDir & "start.bat""" & strArgs, 0, False
