from .category import Ac
import folder_paths
import os
import shutil
import random
import string
from PIL import Image, ImageSequence, ImageOps
import torch
import numpy as np
import av

def pil2tensor(img):
    output_images = []
    output_masks = []
    for i in ImageSequence.Iterator(img):
        i = ImageOps.exif_transpose(i)
        if i.mode == 'I':
            i = i.point(lambda i: i * (1 / 255))
        image = i.convert("RGB")
        image = np.array(image).astype(np.float32) / 255.0
        image = torch.from_numpy(image)[None,]
        if 'A' in i.getbands():
            mask = np.array(i.getchannel('A')).astype(np.float32) / 255.0
            mask = 1. - torch.from_numpy(mask)
        else:
            mask = torch.zeros((64, 64), dtype=torch.float32, device="cpu")
        output_images.append(image)
        output_masks.append(mask.unsqueeze(0))

    if len(output_images) > 1:
        output_image = torch.cat(output_images, dim=0)
        output_mask = torch.cat(output_masks, dim=0)
    else:
        output_image = output_images[0]
        output_mask = output_masks[0]

    return (output_image, output_mask)


def f32_pcm(wav):
    if wav.dtype.is_floating_point:
        return wav
    elif wav.dtype == torch.int16:
        return wav.float() / (2 ** 15)
    elif wav.dtype == torch.int32:
        return wav.float() / (2 ** 31)
    raise ValueError(f"Unsupported wav dtype: {wav.dtype}")


def load_audio(filepath):
    with av.open(filepath) as af:
        if not af.streams.audio:
            raise ValueError("No audio stream found in the file.")

        stream = af.streams.audio[0]
        sr = stream.codec_context.sample_rate
        n_channels = stream.channels

        frames = []
        for frame in af.decode(streams=stream.index):
            buf = torch.from_numpy(frame.to_ndarray())
            if buf.shape[0] != n_channels:
                buf = buf.view(-1, n_channels).t()
            frames.append(buf)

        if not frames:
            raise ValueError("No audio frames decoded.")

        wav = torch.cat(frames, dim=1)
        wav = f32_pcm(wav)
        return wav, sr


class ImageToInput(Ac):
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image_path": ("STRING", {"default": "本地图像路径"}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "image_to_input"

    def image_to_input(self, image_path):
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"图像文件不存在: {image_path}")

        input_dir = folder_paths.get_input_directory()
        file_ext = os.path.splitext(image_path)[1].lower()
        if not file_ext:
            file_ext = ".png"

        random_digits = ''.join(random.choices(string.digits, k=15))
        new_filename = f"{random_digits}{file_ext}"
        dest_path = os.path.join(input_dir, new_filename)

        shutil.copy2(image_path, dest_path)

        img = Image.open(dest_path)
        img_out= pil2tensor(img)

        return (img_out)

class AudioToInput(Ac):
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio_path": ("STRING", {"default": "本音频路径"}),
            }
        }
    RETURN_TYPES = ("AUDIO",)
    FUNCTION = "audio_to_input"

    def audio_to_input(self, audio_path):
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        input_dir = folder_paths.get_input_directory()
        file_ext = os.path.splitext(audio_path)[1].lower()
        if not file_ext:
            file_ext = ".wav"

        random_digits = ''.join(random.choices(string.digits, k=15))
        new_filename = f"{random_digits}{file_ext}"
        dest_path = os.path.join(input_dir, new_filename)

        shutil.copy2(audio_path, dest_path)

        waveform, sample_rate = load_audio(dest_path)
        audio = {"waveform": waveform.unsqueeze(0), "sample_rate": sample_rate}

        return (audio,)