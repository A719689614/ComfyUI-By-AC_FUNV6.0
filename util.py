import io
import oss2
import numpy as np
import requests
import torch
from PIL import Image
from io import BytesIO
import os

OSS_ENDPOINT_LIST = [
    # 中国内地
    "oss-cn-hangzhou.aliyuncs.com",
    "oss-cn-shanghai.aliyuncs.com",
    "oss-cn-qingdao.aliyuncs.com",
    "oss-cn-beijing.aliyuncs.com",
    "oss-cn-shenzhen.aliyuncs.com",
    "oss-cn-heyuan.aliyuncs.com",
    "oss-cn-zhangjiakou.aliyuncs.com",
    "oss-cn-huhehaote.aliyuncs.com",
    "oss-cn-wulanchabu.aliyuncs.com",
    "oss-cn-chengdu.aliyuncs.com",
    "oss-cn-hangzhou-internal.aliyuncs.com",
    "oss-cn-shanghai-internal.aliyuncs.com",
    "oss-cn-qingdao-internal.aliyuncs.com",
    "oss-cn-beijing-internal.aliyuncs.com",
    "oss-cn-shenzhen-internal.aliyuncs.com",
    "oss-cn-heyuan-internal.aliyuncs.com",
    "oss-cn-zhangjiakou-internal.aliyuncs.com",
    "oss-cn-huhehaote-internal.aliyuncs.com",
    "oss-cn-wulanchabu-internal.aliyuncs.com",
    "oss-cn-chengdu-internal.aliyuncs.com",
    # 中国香港
    "oss-cn-hongkong.aliyuncs.com",
    "oss-cn-hongkong-internal.aliyuncs.com",
    # 美国
    "oss-us-west-1.aliyuncs.com",
    "oss-us-east-1.aliyuncs.com",
    "oss-us-west-1-internal.aliyuncs.com",
    "oss-us-east-1-internal.aliyuncs.com",
    # 亚太
    "oss-ap-southeast-1.aliyuncs.com",
    "oss-ap-southeast-2.aliyuncs.com",
    "oss-ap-southeast-3.aliyuncs.com",
    "oss-ap-southeast-5.aliyuncs.com",
    "oss-ap-northeast-1.aliyuncs.com",
    "oss-ap-south-1.aliyuncs.com",
    "oss-ap-southeast-1-internal.aliyuncs.com",
    "oss-ap-southeast-2-internal.aliyuncs.com",
    "oss-ap-southeast-3-internal.aliyuncs.com",
    "oss-ap-southeast-5-internal.aliyuncs.com",
    "oss-ap-northeast-1-internal.aliyuncs.com",
    "oss-ap-south-1-internal.aliyuncs.com",
    # 欧洲
    "oss-eu-central-1.aliyuncs.com",
    "oss-eu-west-1.aliyuncs.com",
    "oss-eu-central-1-internal.aliyuncs.com",
    "oss-eu-west-1-internal.aliyuncs.com",
    # 中东
    "oss-me-east-1.aliyuncs.com",
    "oss-me-east-1-internal.aliyuncs.com"
]


# 将一个图像张量（Tensor）转换成 PIL (Pillow) 图像对象
def tensor_to_pil(image):
    return Image.fromarray(np.clip(255. * image.cpu().numpy().squeeze(), 0, 255).astype(np.uint8))


# Convert PIL to Tensor
def pil_to_tensor(image):
    return torch.from_numpy(np.array(image).astype(np.float32) / 255.0).unsqueeze(0)

# 从url中获取图片
def read_image_from_url(image_url):
    try:
        # 1. 获取图片数据 (推荐开启 verify=True)
        response = requests.get(image_url, stream=True, timeout=15) # 增加超时时间
        response.raise_for_status() # 检查 HTTP 错误
        image_bytes = response.content

        # 2. 打开图片
        pil_image = Image.open(io.BytesIO(image_bytes)).convert('RGB')

        # 3. 转换为 NumPy 数组并归一化
        numpy_image = np.array(pil_image).astype(np.float32) / 255.0

        # 4. 转换为 PyTorch 张量
        tensor_image = torch.from_numpy(numpy_image) # Shape: (H, W, C)

        # 5. 添加 Batch 维度
        batch_tensor = tensor_image.unsqueeze(0) # Shape: (1, H, W, C)

        # 6. 返回符合 ComfyUI 格式的张量
        return (batch_tensor,)

    except requests.exceptions.RequestException as e:
        raise Exception(f"Failed to load image from URL: {image_url}. Error: {e}") from e
    except Exception as e:
        raise Exception(f"Failed to process image from URL: {image_url}. Error: {e}") from e

# 上传图片到oss中
def put_object(file,filename,access_key_id, access_key_secret, security_token,bucket_name, endpoint):
    auth = oss2.StsAuth(access_key_id,access_key_secret,security_token,auth_version = "v2")
    bucket = oss2.Bucket(auth, endpoint, bucket_name)
    image_bytes = BytesIO()
    file.save(image_bytes, format='png')  # 保存为 JPEG 格式
    image_bytes.seek(0)  # 将流指针回到开头
    try:
        bucket.put_object(filename, image_bytes)
    except oss2.exceptions.OssError as e:
        raise ValueError(f'上传失败，错误信息: {e}')

    except Exception as e:
        print(f"OSS 上传失败: {str(e)}")
        return None

# 从oss获取图片
def get_object(object_key, access_key_id, access_key_secret, security_token, bucket_name, endpoint):
    try:
        auth = oss2.StsAuth(access_key_id,access_key_secret,security_token,auth_version = "v2")
        bucket = oss2.Bucket(auth, endpoint, bucket_name)
        object_stream = bucket.get_object(object_key)
        img_data = object_stream.read()
        if not img_data:
            raise ValueError(f"Failed to read data for object: {object_key}")
        image = Image.open(io.BytesIO(img_data))
        image = image.convert("RGB")
        image_np = np.array(image).astype(np.float32)
        image_np /= 255.0
        image_tensor = torch.from_numpy(image_np)
        image_tensor = image_tensor.unsqueeze(0)
        print(f"Successfully loaded image from OSS. Tensor shape: {image_tensor.shape}")
        return (image_tensor,)
    except oss2.exceptions.NoSuchKey:
        raise oss2.exceptions.NoSuchKey(f"Object '{object_key}' not found in bucket '{bucket_name}'.")
    except Exception as e:
        raise e
    finally:
        # 确保 response 被关闭 (oss2 的 get_object 返回的 stream 在 read() 后通常会自动处理，但显式关闭更安全)
        if 'object_stream' in locals() and hasattr(object_stream, 'resp') and object_stream.resp:
            pass

# 获取阿里云ak信息
def get_aliyun_ak(sts_service_url):
    try:
        response = requests.get(sts_service_url)
        response.raise_for_status()
        data = response.json()
        if not data["success"]:
            raise ValueError(f"获取ak失败: {data}")
        return data
    except requests.exceptions.HTTPError as http_err:
        raise ValueError(f"HTTP 错误发生: {http_err}")
    except requests.exceptions.RequestException as req_err:
        raise ValueError(f"请求错误发生: {req_err}")
    except ValueError as value_err:
        raise ValueError(f"JSON 解析错误: {value_err}")
