' Export DOCX to PDF via Word COM (VBScript — more reliable than PowerShell on this machine)
Option Explicit
Dim word, doc, src, dst, pages, i
If WScript.Arguments.Count < 2 Then
  WScript.Echo "Usage: cscript rg_word_export.vbs <input.docx> <output.pdf>"
  WScript.Quit 1
End If
src = WScript.Arguments(0)
dst = WScript.Arguments(1)

On Error Resume Next
Set word = CreateObject("Word.Application")
If Err.Number <> 0 Then
  WScript.Echo "ERR create Word: " & Err.Description
  WScript.Quit 2
End If
On Error GoTo 0

word.Visible = False
word.DisplayAlerts = 0
word.AutomationSecurity = 3 ' msoAutomationSecurityForceDisable

Set doc = word.Documents.Open(src, False, True)
pages = doc.ComputeStatistics(2)
WScript.Echo "PAGES=" & pages
' 17 = wdFormatPDF
doc.SaveAs2 dst, 17
doc.Close False
word.Quit
WScript.Echo "OK"
