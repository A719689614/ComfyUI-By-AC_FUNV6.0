from .category import Ac
import folder_paths
import os
import shutil
import random
import string
from PIL import Image, ImageSequence, ImageOps
import torch
import numpy as np

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


class ImageToInput(Ac):
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("STRING", {"default": "本地图像路径"}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "image_to_input"

    def image_to_input(self, image):
        if not os.path.exists(image):
            raise FileNotFoundError(f"图像文件不存在: {image}")

        input_dir = folder_paths.get_input_directory()
        file_ext = os.path.splitext(image)[1].lower()
        if not file_ext:
            file_ext = ".png"

        random_digits = ''.join(random.choices(string.digits, k=15))
        new_filename = f"{random_digits}{file_ext}"
        dest_path = os.path.join(input_dir, new_filename)

        shutil.copy2(image, dest_path)

        img = Image.open(dest_path)
        img_out= pil2tensor(img)

        return (img_out)