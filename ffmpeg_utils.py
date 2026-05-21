import os
import subprocess
import sys


def ensure_ffmpeg():

    try:
        import imageio_ffmpeg
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        if ffmpeg_path and os.path.exists(ffmpeg_path):
            return ffmpeg_path
    except ImportError:
        pass
    except Exception as e:
        print(f"[FFmpeg Utils] imageio-ffmpeg error: {e}")
    
    # 方法2: 检查系统 PATH 中的 FFmpeg
    system_ffmpeg = _find_system_ffmpeg()
    if system_ffmpeg:
        return system_ffmpeg
    
    # 方法3: 检查本地 bin 目录
    local_ffmpeg = _get_local_ffmpeg_path()
    if os.path.exists(local_ffmpeg):
        return local_ffmpeg
    
    # 都没找到，报错
    raise RuntimeError(
        "FFmpeg not found. Please install it using one of these methods:\n\n"
        "Method 1 (Recommended) - Install imageio-ffmpeg:\n"
        "  pip install imageio-ffmpeg\n\n"
        "Method 2 - Install system FFmpeg:\n"
        "  Windows: Download from https://ffmpeg.org/download.html\n"
        "  Linux: sudo apt install ffmpeg\n"
        "  macOS: brew install ffmpeg"
    )


def _get_local_ffmpeg_path():
    """获取本地 bin 目录中的 FFmpeg 路径"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    bin_dir = os.path.join(current_dir, "bin")
    
    if sys.platform == "win32":
        return os.path.join(bin_dir, "ffmpeg.exe")
    else:
        return os.path.join(bin_dir, "ffmpeg")


def _find_system_ffmpeg():
    """查找系统 PATH 中的 FFmpeg"""
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["where", "ffmpeg"],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            if result.returncode == 0:
                paths = result.stdout.strip().split('\n')
                if paths and paths[0]:
                    return paths[0].strip()
        else:
            result = subprocess.run(
                ["which", "ffmpeg"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
    except Exception:
        pass
    
    return None


def get_ffprobe_path(ffmpeg_path=None):
    """获取 ffprobe 路径 (与 ffmpeg 同目录)"""
    if ffmpeg_path is None:
        ffmpeg_path = ensure_ffmpeg()
    
    # 尝试从 imageio-ffmpeg 获取
    try:
        import imageio_ffmpeg
        # imageio-ffmpeg 不提供 ffprobe，使用同目录推断
        pass
    except ImportError:
        pass
    
    # 推断 ffprobe 路径
    if sys.platform == "win32":
        ffprobe_path = ffmpeg_path.replace('ffmpeg.exe', 'ffprobe.exe')
    else:
        ffprobe_path = ffmpeg_path.replace('ffmpeg', 'ffprobe')
    
    if os.path.exists(ffprobe_path):
        return ffprobe_path
    
    # 尝试系统 ffprobe
    try:
        result = subprocess.run(
            ["ffprobe", "-version"],
            capture_output=True,
            timeout=5
        )
        if result.returncode == 0:
            return "ffprobe"
    except Exception:
        pass
    
    return None
