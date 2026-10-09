@echo off
set PYTHONPATH=C:\Users\VICTUS\MariAnalysis\backend
cd /d C:\Users\VICTUS\MariAnalysis\backend
python -u -m ml.download_image_datasets --root G:\MariAnalysis_Datasets\image --max-gb 20 > dl_stdout.log 2>&1
