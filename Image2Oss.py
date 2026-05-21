from .util import (tensor_to_pil,read_image_from_url,put_object,
                   get_aliyun_ak,OSS_ENDPOINT_LIST,get_object)
import ast
from .category import Ac
import time
import oss2
import random
import string
import os
from datetime import datetime
import folder_paths
import scipy.io.wavfile
import subprocess
import uuid
from .ffmpeg_utils import ensure_ffmpeg

try:
    from comfy_api.input.video_types import VideoFromFile
    HAS_VIDEO_TYPE = True
except ImportError:
    try:
        from comfy_api.latest._input_impl.video_types import VideoFromFile
        HAS_VIDEO_TYPE = True
    except ImportError:
        HAS_VIDEO_TYPE = False
        VideoFromFile = None


_temp_files_to_cleanup = set()
def _upload_with_retry(bucket_obj, oss_path, local_path, max_retries=20, retry_delay=3):
    """Upload a file to OSS with retry mechanism."""
    for attempt in range(max_retries):
        try:
            with open(local_path, "rb") as f:
                bucket_obj.put_object(oss_path, f)
            print(
                f"Successfully uploaded {local_path} to {oss_path} on attempt {attempt + 1}"
            )
            return
        except Exception as e:
            print(f"Upload attempt {attempt + 1}/{max_retries} failed: {str(e)}")
            if attempt + 1 < max_retries:
                print(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                print("Max retries reached. Upload failed.")
                raise e

def _register_temp_file(path):
    """Register a temp file for cleanup on exit"""
    _temp_files_to_cleanup.add(path)


class OSSUploadNode(Ac):
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "filename": ("STRING",{"default":'["tmp-comfyui/filename.png"]'}),
                "access_key_id": ("STRING", {"default": "access_key_id"}),
                "access_key_secret": ("STRING", {"default": "access_key_secret"}),
                "security_token": ("STRING", {"default": ""}),
                "bucket_name": ("STRING", {"default": "bucket_name"}),
                "endpoint": (OSS_ENDPOINT_LIST,{"default": "oss-cn-shenzhen.aliyuncs.com"}),
            }
        }

    # 校验参数是否正确
    @classmethod
    def VALIDATE_INPUTS(cls,image, filename, access_key_id, access_key_secret, bucket_name, endpoint):
        #print("参数校验:\t%s,%s,%s,%s,%s" % (filename, access_key_id, access_key_secret, bucket_name, endpoint))
        if filename == "" or access_key_id == "" or access_key_secret == "" or bucket_name == "" or endpoint == "":
            return "参数不能为空"
        # 检查endpoing
        if endpoint not in OSS_ENDPOINT_LIST:
            return "endpoint 不正确\t %s" % endpoint
        return True
    RETURN_TYPES = ()
    FUNCTION = "upload_to_oss"
    OUTPUT_NODE = True
    def upload_to_oss(self, image, filename, access_key_id, access_key_secret,security_token, bucket_name, endpoint):
        #print("参数信息: \t%s,%s,%s,%s,%s\n" %( filename,access_key_id, access_key_secret, bucket_name, endpoint))

        # 先判断这里是不是字符串
        if not isinstance(filename, str):
            raise ValueError("文件名必须为列表")
        try:
            filenameList = ast.literal_eval(filename)
            if isinstance(filenameList, list):  # 检查解析后的结果是否是列表
                pass
            else:
                raise ValueError("文件名必须为列表")
        except:
            raise ValueError("文件名必须为列表")
        print("共有图片[%s]张,filename[%s]个\n" % (len(image), len(filenameList) ))
        if len(image)!= len(filenameList) :
            raise ValueError("生成图片数量与给定的文件名数量不对应")
        n = 0
        for i in image:
            img = tensor_to_pil(i)
            #print("文件名称: [%s] \t文件类型: %s" % (filenameList[n],type(img)))
            put_object(img,filenameList[n],access_key_id, access_key_secret, security_token,bucket_name, endpoint)
            n = n + 1

        return ()

class OSSAudioUploader(Ac):
    """ComfyUI node for uploading audio to Alibaba Cloud OSS"""

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "endpoint": (OSS_ENDPOINT_LIST,{"default": "oss-cn-shenzhen.aliyuncs.com"}),
                "bucket": (
                    "STRING",
                    {
                        "default": "cck-sh",
                        "multiline": False,
                        "placeholder": "OSS bucket name",
                    },
                ),
                "access_key": (
                    "STRING",
                    {"default": "", "multiline": False, "placeholder": "Access Key ID"},
                ),
                "access_secret": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "placeholder": "Access Key Secret",
                    },
                ),
                "path": (
                    "STRING",
                    {
                        "default": "tmp-comfyui/audio",
                        "multiline": False,
                    },
                ),
                "random_filename": ("BOOLEAN", {"default": True}),
                "filename": (
                    "STRING",
                    {
                        "default": "audio.mp3",
                        "multiline": False,
                        "placeholder": "Filename (only used when random_filename is False)",
                    },
                ),
                }
            }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("url",)
    FUNCTION = "upload_audio"

    def generate_random_filename(self, extension: str = "wav") -> str:
        """Generate random filename with timestamp and random string"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        random_str = "".join(
            random.choices(string.ascii_lowercase + string.digits, k=8)
        )
        return f"{timestamp}_{random_str}.{extension}"

    def upload_audio(
        self,
        audio,
        endpoint,
        bucket,
        access_key,
        access_secret,
        path,
        random_filename,
        filename,
    ):
        """Upload audio to OSS and return URL"""
        try:
            # This will trigger the LazyAudioMap if that's what is passed
            waveform = audio["waveform"]
            sample_rate = audio["sample_rate"]

            # Generate filename
            if random_filename:
                filename = self.generate_random_filename("wav")

            if not filename.lower().endswith((".wav", ".mp3", ".flac")):
                filename += ".wav"

            # Prepare temp file path
            temp_path = os.path.join(folder_paths.get_temp_directory(), filename)

            # Save audio to temporary file
            waveform_np = waveform.cpu().numpy()
            if len(waveform_np.shape) == 3:
                waveform_np = waveform_np[0]

            if (
                len(waveform_np.shape) == 2
                and waveform_np.shape[0] < waveform_np.shape[1]
            ):
                waveform_np = waveform_np.T

            scipy.io.wavfile.write(temp_path, sample_rate, waveform_np)

            # Setup OSS auth and upload
            auth = oss2.Auth(access_key, access_secret)
            bucket_obj = oss2.Bucket(auth, endpoint, bucket)
            oss_path = os.path.join(path, filename).replace("\\", "/")

            _upload_with_retry(bucket_obj, oss_path, temp_path)

            os.remove(temp_path)

            # Construct URL
            if endpoint.startswith("https://"):
                base_url = endpoint.replace("https://", f"https://{bucket}.")
            elif endpoint.startswith("http://"):
                base_url = endpoint.replace("http://", f"http://{bucket}.")
            else:
                base_url = f"https://{bucket}.{endpoint}"

            file_url = f"{base_url}/{oss_path}"

            print(f"Audio uploaded successfully to: {file_url}")
            return (file_url,)

        except Exception as e:
            print(f"Error uploading audio to OSS: {str(e)}")
            return (f"Error: {str(e)}",)


class OSSUploadNodeBySTSServiceUrl(Ac):
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "filename": ("STRING",{"default":'["tmp-comfyui/filename.png"]'}),
                "sts_service_url": ("STRING", {"default": "https://demo.cn/sts_service"}),
                "bucket_name": ("STRING", {"default": "bucket_name"}),
                "endpoint": (OSS_ENDPOINT_LIST,{"default": "oss-cn-shenzhen.aliyuncs.com"}),
            }
        }
        # 校验参数是否正确
    @classmethod
    def VALIDATE_INPUTS(cls,image, filename, sts_service_url, bucket_name, endpoint):
        if filename == "" or sts_service_url == "" or bucket_name == "" or endpoint == "":
            return "参数不能为空"
        # 检查endpoing
        if endpoint not in OSS_ENDPOINT_LIST:
            return "endpoint 不正确\t %s" % endpoint
        return True
    RETURN_TYPES = ()
    FUNCTION = "upload_to_oss"
    OUTPUT_NODE = True
    def upload_to_oss(self, image, filename, sts_service_url, bucket_name, endpoint):
        # 先判断这里是不是字符串
        if not isinstance(filename, str):
            raise ValueError("文件名必须为列表")
        try:
            filenameList = ast.literal_eval(filename)
            if isinstance(filenameList, list):  # 检查解析后的结果是否是列表
                pass
            else:
                raise ValueError("文件名必须为列表")
        except:
            raise ValueError("文件名必须为列表")
        if len(image)!= len(filenameList) :
            raise ValueError("生成图片数量与给定的文件名数量不对应")
        data = get_aliyun_ak(sts_service_url)
        access_key_id = data["data"]["accessKeyId"]
        access_key_secret = data["data"]["accessKeySecret"]
        security_token = data["data"]["securityToken"]

        n = 0
        for i in image:
            img = tensor_to_pil(i)
            put_object(img,filenameList[n],access_key_id, access_key_secret, security_token,bucket_name, endpoint)
            n = n + 1

        return ()


class LoadImageFromURL(Ac):
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image_url": ("STRING",{"default":"https://gd-hbimg.huaban.com/5c6487e9ef2d4e4840082b0671cf3a86f8139eb430c1b-dLDkjJ_fw658webp"}),
            }
        }
    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "load_image"
    def load_image(self, image_url):
        return read_image_from_url(image_url)
 
class LoadImageFromOss(Ac):
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "filename": ("STRING",{"default":"tmp/screenshot.png"}),
                "access_key_id": ("STRING", {"default": "access_key_id"}),
                "access_key_secret": ("STRING", {"default": "access_key_secret"}),
                "security_token": ("STRING", {"default": ""}),
                "bucket_name": ("STRING", {"default": "bucket_name"}),
                "endpoint": (OSS_ENDPOINT_LIST,{"default": "oss-cn-shenzhen.aliyuncs.com"}),
            }
        }
    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "load_image"
    def load_image(self, filename, access_key_id, access_key_secret, security_token, bucket_name, endpoint):
        return get_object(filename, access_key_id, access_key_secret, security_token, bucket_name, endpoint)
    
class LoadImageFromOssBySTSServiceUrl(Ac):
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "filename": ("STRING",{"default":"comfyui/filename.png"}),
                "sts_service_url": ("STRING", {"default": "https://demo.cn/sts_service"}),
                "bucket_name": ("STRING", {"default": "bucket_name"}),
                "endpoint": (OSS_ENDPOINT_LIST,{"default": "oss-cn-shenzhen.aliyuncs.com"}),
            }
        }
    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "load_image"
    def load_image(self, filename, sts_service_url,  bucket_name, endpoint):
        data = get_aliyun_ak(sts_service_url)
        access_key_id = data["data"]["accessKeyId"]
        access_key_secret = data["data"]["accessKeySecret"]
        security_token = data["data"]["securityToken"]
        return get_object(filename, access_key_id, access_key_secret, security_token, bucket_name, endpoint)
    

# 从ulr加载音频
class LoadAudioFromURL(Ac):
    """Load audio from URL"""
    
    def __init__(self):
        self.temp_dir = folder_paths.get_temp_directory()
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "url": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "Enter audio URL, e.g. https://example.com/audio.mp3",
                    "dynamicPrompts": False
                }),
                "show_preview": ("BOOLEAN", {"default": True}),
            },
        }

    RETURN_TYPES = ("AUDIO",)
    RETURN_NAMES = ("AUDIO",)
    FUNCTION = "load_audio_url"

    def load_audio_url(self, url, show_preview=True):
        import requests
        import torch
        
        if not url or not url.strip():
            return (None,)
        
        url = url.strip()
        
        # Download audio to temp file
        try:
            # Generate temp file path
            ext = os.path.splitext(url.split('?')[0])[-1] or '.mp3'
            if ext.lower() not in ['.mp3', '.wav', '.aac', '.flac', '.ogg', '.m4a']:
                ext = '.mp3'
            temp_path = os.path.join(self.temp_dir, f"ffmpeg_url_audio_{uuid.uuid4().hex[:8]}{ext}")
            
            # Download audio
            response = requests.get(url, stream=True, timeout=60)
            response.raise_for_status()
            
            with open(temp_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Convert to WAV using FFmpeg for consistent format
            ffmpeg_path = ensure_ffmpeg()
            wav_path = os.path.join(self.temp_dir, f"ffmpeg_url_audio_{uuid.uuid4().hex[:8]}.wav")
            
            # Register temp files for cleanup
            _register_temp_file(temp_path)
            _register_temp_file(wav_path)
            
            cmd = [
                ffmpeg_path, "-y",
                "-i", temp_path,
                "-acodec", "pcm_s16le",
                "-ar", "44100",
                "-ac", "2",
                wav_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"[FFmpeg] FFmpeg conversion failed: {result.stderr}")
                raise RuntimeError(f"FFmpeg conversion failed: {result.stderr}")
            
            # Load audio using torchaudio (preferred) or fallback methods
            waveform = None
            sample_rate = 44100
            
            # Method 1: Try torchaudio (preferred)
            try:
                import torchaudio
                waveform, sample_rate = torchaudio.load(wav_path)
                
                # Add batch dimension if needed [B, C, S]
                if len(waveform.shape) == 2:
                    waveform = waveform.unsqueeze(0)
                    
            except ImportError:
                print("[FFmpeg] torchaudio not available, trying fallback methods...")
            except Exception as e:
                print(f"[FFmpeg] torchaudio load failed: {e}, trying fallback methods...")
            
            # Method 2: Try scipy.io.wavfile
            if waveform is None:
                try:
                    from scipy.io import wavfile
                    sample_rate, audio_data = wavfile.read(wav_path)
                    import numpy as np
                    
                    # Normalize to float32 [-1, 1]
                    if audio_data.dtype == np.int16:
                        audio_data = audio_data.astype(np.float32) / 32768.0
                    elif audio_data.dtype == np.int32:
                        audio_data = audio_data.astype(np.float32) / 2147483648.0
                    elif audio_data.dtype == np.uint8:
                        audio_data = (audio_data.astype(np.float32) - 128) / 128.0
                    
                    # Handle mono vs stereo
                    if len(audio_data.shape) == 1:
                        audio_data = audio_data.reshape(1, -1)  # [C, S]
                    else:
                        audio_data = audio_data.T  # [S, C] -> [C, S]
                    
                    waveform = torch.from_numpy(audio_data).unsqueeze(0)  # [1, C, S]
                    print("[FFmpeg] Loaded audio using scipy.io.wavfile")
                    
                except ImportError:
                    print("[FFmpeg] scipy not available, trying manual WAV parsing...")
                except Exception as e:
                    print(f"[FFmpeg] scipy load failed: {e}, trying manual WAV parsing...")
            
            # Method 3: Manual WAV parsing (basic fallback)
            if waveform is None:
                try:
                    import wave
                    import numpy as np
                    
                    with wave.open(wav_path, 'rb') as wav_file:
                        n_channels = wav_file.getnchannels()
                        sample_width = wav_file.getsampwidth()
                        sample_rate = wav_file.getframerate()
                        n_frames = wav_file.getnframes()
                        
                        raw_data = wav_file.readframes(n_frames)
                        
                        # Convert bytes to numpy array
                        if sample_width == 2:
                            audio_data = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0
                        elif sample_width == 1:
                            audio_data = (np.frombuffer(raw_data, dtype=np.uint8).astype(np.float32) - 128) / 128.0
                        else:
                            raise ValueError(f"Unsupported sample width: {sample_width}")
                        
                        # Reshape for channels
                        if n_channels > 1:
                            audio_data = audio_data.reshape(-1, n_channels).T  # [C, S]
                        else:
                            audio_data = audio_data.reshape(1, -1)  # [1, S]
                        
                        waveform = torch.from_numpy(audio_data).unsqueeze(0)  # [1, C, S]
                        print("[FFmpeg] Loaded audio using manual WAV parsing")
                        
                except Exception as e:
                    print(f"[FFmpeg] Manual WAV parsing failed: {e}")
                    raise RuntimeError(
                        f"Cannot load audio file. Please install torchaudio or scipy:\n"
                        f"  pip install torchaudio\n"
                        f"  or: pip install scipy"
                    )
            
            # Return ComfyUI standard AUDIO format
            audio_output = {
                "waveform": waveform,
                "sample_rate": sample_rate
            }
            return (audio_output,)
                
        except Exception as e:
            print(f"[FFmpeg] Failed to download/process audio from URL: {e}")
            raise RuntimeError(f"Failed to download/process audio from URL: {e}")


#  从URL加载视频 =============================================================================================================
class LoadVideoFromURL(Ac):
    def __init__(self):
        self.temp_dir = folder_paths.get_temp_directory()
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "url": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "Enter video URL, e.g. https://example.com/video.mp4",
                    "dynamicPrompts": False
                }),
                "show_preview": ("BOOLEAN", {"default": True}),
            },
        }

    RETURN_TYPES = ("VIDEO",)
    RETURN_NAMES = ("VIDEO",)
    FUNCTION = "load_video_url"

    def load_video_url(self, url, show_preview=True):
        import requests
        
        if not url or not url.strip():
            return (None,)
        
        url = url.strip()
        
        # Download video to temp file for compatibility with ComfyUI native nodes
        try:
            # Generate temp file path
            ext = os.path.splitext(url.split('?')[0])[-1] or '.mp4'
            if ext not in ['.mp4', '.mov', '.avi', '.mkv', '.webm']:
                ext = '.mp4'
            temp_path = os.path.join(self.temp_dir, f"ffmpeg_url_video_{uuid.uuid4().hex[:8]}{ext}")
            
            # Download video
            response = requests.get(url, stream=True, timeout=60)
            response.raise_for_status()
            
            with open(temp_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Register for cleanup on exit
            _register_temp_file(temp_path)
            
            # Return VideoFromFile if available, otherwise return path
            if HAS_VIDEO_TYPE and VideoFromFile is not None:
                return (VideoFromFile(temp_path),)
            else:
                return (temp_path,)
                
        except Exception as e:
            print(f"[FFmpeg] Failed to download video from URL: {e}")
            raise RuntimeError(f"Failed to download video from URL: {e}")

# 视频上传到Oss ===========================================================================================================
# class OSSVideoUploader(Ac):
#     """ComfyUI node for uploading videos to Alibaba Cloud OSS"""

#     def __init__(self):
#         pass

#     @classmethod
#     def INPUT_TYPES(cls):
#         return {
#             "required": {
#                 "video": ("VIDEO",),
#                 "endpoint": (OSS_ENDPOINT_LIST,{"default": "oss-cn-shenzhen.aliyuncs.com"}),
#                 "bucket": (
#                     "STRING",
#                     {
#                         "default": "cck-sh",
#                         "multiline": False,
#                         "placeholder": "OSS bucket name",
#                     },
#                 ),
#                 "access_key": (
#                     "STRING",
#                     {"default": "", "multiline": False, "placeholder": "Access Key ID"},
#                 ),
#                 "access_secret": (
#                     "STRING",
#                     {
#                         "default": "",
#                         "multiline": False,
#                         "placeholder": "Access Key Secret",
#                     },
#                 ),
#                 "path": (
#                     "STRING",
#                     {
#                         "default": "tmp-comfyui/video",
#                         "multiline": False,
#                         "placeholder": "OSS path (e.g., aigc/up)",
#                     },
#                 ),
#                 "random_filename": ("BOOLEAN", {"default": True}),
#                 "filename": (
#                     "STRING",
#                     {
#                         "default": "video.mp4",
#                         "multiline": False,
#                         "placeholder": "Filename (only used when random_filename is False)",
#                     },
#                 ),
#             }
#         }

#     RETURN_TYPES = ("STRING",)
#     RETURN_NAMES = ("url",)
#     FUNCTION = "upload_video"

#     def generate_random_filename(self, extension: str = "mp4") -> str:
#         """Generate random filename with timestamp and random string"""
#         timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
#         random_str = "".join(
#             random.choices(string.ascii_lowercase + string.digits, k=8)
#         )
#         return f"{timestamp}_{random_str}.{extension}"

#     def upload_video(
#         self,
#         video,
#         endpoint,
#         bucket,
#         access_key,
#         access_secret,
#         path,
#         random_filename,
#         filename,
#     ):
#         """Upload video to OSS and return URL"""
#         try:
#             video_path = None
#             if isinstance(video, (list, tuple)) and len(video) >= 2:
#                 if isinstance(video[0], bool) and isinstance(
#                     video[1], (list, tuple)
#                 ):
#                     video_files = [
#                         f
#                         for f in video[1]
#                         if f.lower().endswith(
#                             (".mp4", ".avi", ".mov", ".webm", ".mkv", ".gif")
#                         )
#                     ]
#                     if video_files:
#                         video_path = video_files[-1]
#                 else:
#                     for item in video:
#                         if isinstance(item, str) and item.lower().endswith(
#                             (".mp4", ".avi", ".mov", ".webm", ".mkv", ".gif")
#                         ):
#                             video_path = item
#                             break
#                     if not video_path:
#                         video_path = video[0] if video else None
#             elif isinstance(video, str):
#                 video_path = video

#             if not video_path:
#                 return (
#                     f"Error: Could not extract video path from input. Input was: {video}",
#                 )

#             if not os.path.exists(video_path):
#                 print(f"[WARNING] Video file may not exist yet: {video_path}")

#             _, ext = os.path.splitext(video_path)
#             ext = ext if ext else ".mp4"

#             if random_filename:
#                 filename = self.generate_random_filename(ext.lstrip("."))
#             else:
#                 if not filename.lower().endswith(
#                     (".mp4", ".avi", ".mov", ".webm", ".mkv", ".gif")
#                 ):
#                     filename += ext

#             auth = oss2.Auth(access_key, access_secret)
#             bucket_obj = oss2.Bucket(auth, endpoint, bucket)

#             oss_path = os.path.join(path, filename).replace("\\", "/")

#             _upload_with_retry(bucket_obj, oss_path, video_path)

#             if endpoint.startswith("https://"):
#                 base_url = endpoint.replace("https://", f"https://{bucket}.")
#             elif endpoint.startswith("http://"):
#                 base_url = endpoint.replace("http://", f"http://{bucket}.")
#             else:
#                 base_url = f"https://{bucket}.{endpoint}"

#             file_url = f"{base_url}/{oss_path}"

#             print(f"Video uploaded successfully to: {file_url}")
#             return (file_url,)

#         except Exception as e:
#             print(f"Error uploading video to OSS: {str(e)}")
#             return (f"Error: {str(e)}",)