@echo off
setlocal
cd /d C:\Users\yoeld\Documents\youtube-bot
if not exist logs mkdir logs
python scheduler.py --once --videos-per-day 3 >> logs\daily_3_videos.log 2>&1
endlocal
