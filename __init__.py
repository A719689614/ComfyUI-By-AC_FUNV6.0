from .load_image_url_node import LoadImageByUrl
from .Image2Oss import OSSUploadNode, OSSUploadNodeBySTSServiceUrl, OSSAudioUploader, LoadAudioFromURL, LoadVideoFromURL
from .Image2Oss import LoadImageFromURL, LoadImageFromOss, LoadImageFromOssBySTSServiceUrl
from .image_to_input import ImageToInput

NODE_CLASS_MAPPINGS = {
    "AC_从URL加载图像":LoadImageByUrl,
    "AC_路径加载图像":ImageToInput,
    "AC_Oss上传图像":OSSUploadNode,
    "AC_从URL加载音频":LoadAudioFromURL,
    "AC_Oss上传音频":OSSAudioUploader,
    "AC_从URL加载视频":LoadVideoFromURL,
    # "AC_Oss上传视频":OSSVideoUploader,
    "AC_Oss上传服务":OSSUploadNodeBySTSServiceUrl,
    "AC_从URL加载图像":LoadImageFromURL,
    "AC_从Oss加载图像":LoadImageFromOss,
    "AC_从Oss加载图像(使用服务)":LoadImageFromOssBySTSServiceUrl
}
