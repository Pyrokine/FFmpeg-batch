import shutil
import subprocess
import os
import re
import json
import time
from pprint import pprint

format_filter = ['.mp4', '.mkv', '.webm', '.avi', '.flv', '.mov', '.wmv', '.3gp',
                 '.mpg', '.mpeg', '.vob', '.swf', '.rm', '.rmvb', '.m4v', '.ts']  # 完整格式支持通过 [.\ffmpeg.exe -formats] 查看
source_folder_name = 'source'
target_folder_name = 'target'
force_overwrite = True  # 强制覆盖目标文件夹中已有的文件
need_copy_other_files = True  # 是否复制其他非视频文件
quality = 18


def extract_progress(process, source_info):
    start_time = time.time()
    re_pattern = re.compile(r'time=([0-9]+):([0-9]+):([0-9]+).([0-9]+)')
    for line in process.stdout:
        cur_duration, total_duration = re.findall(re_pattern, line), float(source_info['f:duration'])
        if cur_duration:
            cur_duration = cur_duration[0]
            cur_duration = (((int(cur_duration[0]) * 60) + int(cur_duration[1])) * 60 + int(cur_duration[2]))
            progress = cur_duration / total_duration
            print("\r{0:^3.2f}% [{1:-<50}] 剩余时间：{2:.2f}s".format(
                progress * 100, '▓' * int(50 * progress), (time.time() - start_time) * (1.0 - progress) / (progress + 1e-6)), end="")
            time.sleep(0.01)
    print('\r100.0% [▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓] 转换耗时：{0:.2f}s'.format(time.time() - start_time))


def convert_to_h265(source_file, target_file, source_info):
    parameters = {
        # ######### 视频流基础设置 ##########
        '-c:v': 'hevc_nvenc',  # N卡使用hevc_nvenc，A卡使用hevc_amf，I卡使用hevc_qsv，CPU only则用libx265，后续参数适用nvenc，其他编译器参数需自行查阅（建议在源码里查阅）
        '-preset:v': 'p7',  # nvenc里p1到p7预设从低到高，后续的设置会覆盖其中的对应项
        '-profile:v': 'main10',  # main10最高支持10bits位深，main则为8bits，但若pix_fmt设置了更高的位深（似乎）会自适应到main10或rext
        '-pix_fmt:v': 'p010',  # 使用常见的YUV格式，hevc_nvenc支持[8bits的yuv420p、yuv444p]和[10bits的p010]和[截断到10bits的p016、yuv444p16]，默认为le
        # '-tier:v': 'main',  # 设置到high可以支持更高的位深和更广的色域，profile里似乎没有和high相关的设置
        # '-level:v': '6.2',  # 不同level支持的最高码率帧率位深等参数不同，具体可以在维基中查阅，ffmpeg会自适应，所以不用设置
        '-b:v': '0',  # 比特率控制设置为无限制（不设置也可以）
        '-maxrate:v': '0',  # 最大比特率设置为无限制（不设置也可以）
        '-bufsize:v': '0',  # 缓存大小设置为无限制（不设置也可以）
        # '-s:v': '1920x1080',  # 分辨率为1920x1080，格式为[宽x高]
        # '-r:v': '60',  # 帧率为60
        # '-ss:v': '00:00:00',  # 裁剪开始时间，格式为[时:分:秒]
        # '-t:v': '00:01:00',  # 裁剪时长，格式为[时:分:秒]
        # ----------------------------------------------------------------------------------------------------
        # ######### 视频流滤镜设置 ##########
        # '-vf:v': '"scale=1920:1080, transpose=1, transpose=1, fps=60"',
        # '-vf:v': '"trim=start=0:end=60, setpts=PTS-STARTPTS"',
        # '-vf:v': '"eq=contrast=1:brightness=0:saturation=1.0:gamma=1.0"',
        # 所有vf参数都需要写在一个双引号内，滤镜种类非常多，可以自行查阅，不同滤镜间用逗号隔开，同一个滤镜的不同参数用冒号隔开
        # 另一种设置分辨率方法，格式为[scale=宽:高]，两个均指定则缩放到对应分辨率，其中一个为[-1]则另一个参数按比例自动缩放，如[1920:-1]和[-1:1080]， 另一种设置帧率的方法，格式为[fps=60]
        # 另一种裁剪时间的方法，格式为[trim=start=0:end=60]，[trim=start=0:duration=60]，以秒为单位，以帧为单位则用[start_frame]和[end_frame]
        # Cont. 需要同时裁剪音频否则文件时长是不变的，语法相同，并且需要添加[setpts=PTS-STARTPTS]以使时间戳从0开始，为了省事建议用[-ss]和[-t]实现
        # 顺时针旋转90度为[transpose=1]，逆时针旋转90度为[transpose=2]，旋转180度为[transpose=2, transpose=2], 水平翻转为[hflip]，垂直翻转为[vflip]
        # 裁减[crop=w:h:x:y]（左上角像素坐标及宽高），调整对比度[contrast=1.2]（-1000.0-1000.0，默认为1），调整亮度[brightness=0.5]（-1.0-1.0，默认为0）等等
        # ----------------------------------------------------------------------------------------------------
        # ######### 视频流码率控制 ##########
        # 两种模式选择一种开启即可，quality数值越低视频质量越高，一般认为低于18的差异无法用肉眼分辨
        # constqp模式中四个参数设置为相同值和vbr模式三个参数设置为相同值输出的文件是完全相同的
        # ----- Constant Quantization Parameter mode -----
        # '-rc:v': 'constqp',  # 码率控制模式
        # '-qp:v': quality,  #
        # '-init_qpP:v': quality,
        # '-init_qpB:v': quality,
        # '-init_qpI:v': quality,
        # ----- Variable bitrate mode -----
        # '-rc:v': 'vbr',
        '-cq:v': quality,
        '-qmin:v': 0,
        '-qmax:v': 21,
        # ----------------------------------------------------------------------------------------------------
        # ######### 视频流额外设置 ##########
        # 非必需参数，可以尝试开启
        # '-tune:v': 'lossless',  # 
        # '-rc-lookahead:v': 60,  # 预读帧以预测并控制码率，默认值为60
        # '-sc_threshold:v': '0',  # 场景切换检测阈值（0.0-1.0），若相邻两帧的差异超过阈值则编码器可能会重新选择编码参数以适应新场景，过高可能会导致质量降低，过低可能会导致编码效率降低，0则为禁用检测
        # '-g:v': '250',  # 连续两个I帧间的帧数（1-600），默认值为250，当超过阈值sc_threshold时会插入一个I帧生成新的GOP
        # '-refs:v': '1',  # 可以参考的最大帧数（1-16），x264默认是3，x265默认是1，增加参考帧数可以提高编码效率，但也会增加编码时间和码率
        # '-bf:v': '5',  # 一个GOP里能插入的B帧数量（0-16），x264默认是3，x265默认是5，增加B帧数量可以提高压缩率，但也会增加编码器的计算复杂度和解码的延迟
        # '-spatial_aq:v': '1',  # 空间自适应量化，用以控制视频质量和码率之间的平衡，在保证高质量的同时减小视频文件大小
        # '-aq-strength:v': '7',  # 自适应量化强度，较低的值可以提高图像质量但会增加码率，反而反之，范围为1-15
        # '-weighted_pred:v': '1',  # 用以加权预测，允许在预测过程中根据像素的特性调整加权，以提高预测精度和视觉质量
        # ----------------------------------------------------------------------------------------------------
        # ######### 音频流基础设置 ##########
        # '-c:a': 'aac',  # 编码器为aac
        # '-b:a': '320k',  # 码率为320kbps
        # '-ar:a': '48000',  # 采样率为48000Hz
        # '-ac:a': '2',  # 设置通道数为2
        # ----------------------------------------------------------------------------------------------------
        # ######### 音频流滤镜设置 ##########
        # '-af:a': '"atrim=duration=1, asetpts=PTS-STARTPTS"',
        # 裁剪语法同视频流，还有其他设置如回声、增益、淡入淡出和循环等，需自行查阅
    }

    command = 'ffmpeg {0} -i "{1}" {2} "{3}"'.format(
        '-y' if force_overwrite else '',
        source_file,
        ' '.join(['{} {}'.format(key, value) for key, value in zip(parameters.keys(), parameters.values())]),
        target_file
    )

    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='UTF-8', text=True)
    extract_progress(process, source_info)

    target_info = extract_video_info(target_file)
    for item in ['f:file_size', 'f:duration', 'f:bitrate', 'f:duration_fmt', 'v:codec', 'v:profile', 'v:level',
                 'v:width', 'v:height', 'v:pix_fmt', 'v:fps', 'a:codec', 'a:sample_rate', 'a:bit_rate', 'a:channels']:
        print('{0: <15}| {1: <12}-> {2}'.format(
            item, source_info[item], target_info[item]
        ))


def extract_video_info(file_path):
    info = {}

    process = subprocess.run(
        'ffprobe.exe -v error -of json -show_format -i {}'.format(file_path),
        shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='UTF-8', text=True
    )
    ori_info = json.loads(str(process.stdout))['format']
    info['f:file_size'] = '{0:.2f}MB'.format(int(ori_info['size']) / 10 ** 6)
    info['f:duration'] = ori_info['duration']
    info['f:bitrate'] = '{}mbps'.format(round(int(ori_info['bit_rate']) / 1000000, 1))

    secs, msecs = divmod(float(info['f:duration']), 1)
    mins, secs = divmod(secs, 60)
    hours, mins = divmod(mins, 60)
    info['f:duration_fmt'] = '{:0>2}:{:0>2}:{:0>2}.{:0>2}'.format(int(hours), int(mins), int(secs), int(msecs * 100))
    info['f:duration'] = round(float(ori_info['duration']), 2)

    process = subprocess.run(
        'ffprobe.exe -v error -of json -show_streams -i {}'.format(file_path),
        shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='UTF-8', text=True
    )
    ori_info = json.loads(str(process.stdout))['streams']

    for stream in ori_info:
        if stream['codec_type'] == 'video':
            info['v:codec'] = stream['codec_name']
            info['v:profile'] = stream['profile']
            info['v:level'] = stream['level']
            info['v:width'] = stream['width']
            info['v:height'] = stream['height']
            info['v:pix_fmt'] = stream['pix_fmt']
            info['v:fps'] = round(eval(stream['r_frame_rate']), 2)
        elif stream['codec_type'] == 'audio':
            info['a:codec'] = stream['codec_name']
            info['a:sample_rate'] = '{}Hz'.format(stream['sample_rate'])
            info['a:bit_rate'] = '{}kbps'.format(int(int(stream['bit_rate']) / 1000))
            info['a:channels'] = stream['channels']
        elif stream['codec_type'] == 'subtitle':
            if 's:subtitle' not in info:
                info['s:subtitle'] = {stream['index']: stream['tags']['language']}
            else:
                info['s:subtitle'][stream['index']] = stream['tags']['language']

    # pprint(info)
    return info


def extract_subtitle(source_file, target_file, source_info):
    if 's:subtitle' not in source_info:
        return

    print('检测到字幕，开始生成字幕文件')
    if len(source_info['s:subtitle']) == 1:
        process = subprocess.Popen(
            'ffmpeg.exe -y -i {0} -map 0:s:0 -c:s ass {1}.ass'.format(source_file, target_file),
            shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='UTF-8', text=True
        )
        extract_progress(process, source_info)
    else:
        for idx, lang in source_info['s:subtitle'].items():
            process = subprocess.Popen(
                'ffmpeg.exe -y -i {0} -map 0:{2} -c:s ass {1}.{2}_{3}.ass'.format(source_file, target_file, idx, lang),
                shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='UTF-8', text=True
            )
            extract_progress(process, source_info)


if __name__ == '__main__':
    for root, dirs, files in os.walk('source'):
        for file in files:
            file_name, file_format = os.path.splitext(file)
            is_video = file_format.lower() in format_filter

            source_file_path = os.path.join(root, file)
            sub_folder_path = root[len(source_folder_name):]
            target_folder_path = os.path.join(target_folder_name, sub_folder_path)
            print('{} | {}'.format(os.path.join(sub_folder_path, file), 'is_video' if is_video else 'not_video'))

            if not os.path.exists(target_folder_path):
                os.makedirs(target_folder_path)

            if is_video:
                source_info = extract_video_info(source_file_path)
                convert_to_h265(
                    source_file_path,
                    os.path.join(target_folder_path, file_name + '.mp4'),
                    source_info
                )
                extract_subtitle(
                    source_file_path,
                    os.path.join(target_folder_path, file_name),
                    source_info
                )
            else:
                if need_copy_other_files:
                    shutil.copy(
                        source_file_path,
                        os.path.join(target_folder_path, file),
                    )
                    print('复制完成')
                else:
                    print('忽略此文件')

            print('------------------------------------------------------------')