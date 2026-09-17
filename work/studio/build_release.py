from pathlib import Path
import subprocess,sys,shutil,pefile
root=Path(__file__).resolve().parent
workspace=root.parent.parent
ocr=root/'bundle/ocr';ocr.mkdir(parents=True,exist_ok=True)
source=Path(__import__('os').environ.get('TESSERACT_HOME','C:/Program Files/Tesseract-OCR'))
if not (source/'tesseract.exe').exists():raise SystemExit('Install Tesseract OCR or set TESSERACT_HOME first.')
todo=[source/'tesseract.exe'];seen=set()
while todo:
 p=todo.pop()
 if p.name.lower() in seen:continue
 seen.add(p.name.lower());shutil.copy2(p,ocr/p.name)
 pe=pefile.PE(str(p))
 for entry in getattr(pe,'DIRECTORY_ENTRY_IMPORT',[]):
  dependency=source/entry.dll.decode()
  if dependency.exists():todo.append(dependency)
 pe.close()
(ocr/'tessdata').mkdir(exist_ok=True)
shutil.copy2(source/'tessdata/eng.traineddata',ocr/'tessdata/eng.traineddata')
out=Path(__import__('os').environ.get('COLOR_STUDIO_DIST',str(workspace/'outputs/release')))
saved=out/'ColorStudio/data'
if saved.exists():shutil.copytree(saved,root/'release-test-data',dirs_exist_ok=True)
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--onedir','--windowed','--name','ColorStudio','--distpath',str(out),'--workpath',str(root/'build'),'--specpath',str(root),'--collect-data','customtkinter','--collect-data','opencc','--add-data',str(ocr)+';ocr','--exclude-module','PySide6','--exclude-module','pandas','--exclude-module','matplotlib',str(root/'app.py')],check=True)
licenses=out/'ColorStudio/THIRD_PARTY';licenses.mkdir(exist_ok=True)
if (source/'doc').exists():shutil.copytree(source/'doc',licenses/'tesseract',dirs_exist_ok=True)
for name in ('README.md','README.zh-TW.md','README.en.md','VALIDATION.md'):
 p=workspace/'outputs'/name
 if p.exists():shutil.copy2(p,out/'ColorStudio'/name)
print('RELEASE',out/'ColorStudio/ColorStudio.exe')
