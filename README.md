# FFmpeg batch

当前版本的 FFmpeg 为 5.1.2 (2022-09-26).

本程序可以将 [source] 文件夹里所有可识别的视频格式转换为 [H265] 并保存到 [target] 文件夹，
可以在程序里设置其他非视频文件是否需要复制到目标文件夹（默认为复制），即可以获得一个目录结构与源文件夹完全相同的同时视频格式为 H265 的文件夹，
相关参数可以根据个人需求自行调整，具体支持的参数建议在 FFmpeg 源码中查阅

直接执行源码需要安装 [python] 并安装依赖 [requirements.txt] ，安装完成后运行 [main.py] 即可。也可以直接运行可执行文件 [main.exe]

打包为可执行文件的命令为 [nuitka --standalone --onefile main.py] ，需要通过 [pip] 安装 [nuitka]

FFmpeg下载地址
https://ffmpeg.org/download.html

视频质量分析工具
https://github.com/zymill/hysVideoQC

解锁N卡编码并行线程数
https://github.com/keylase/nvidia-patch