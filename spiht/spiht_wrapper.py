from dataclasses import dataclass
from typing import List, Optional
import numpy as np
import pywt

from . import spiht as spiht_rs
from .color_spaces import rgb_to_ipt, ipt_to_rgb

def quantize(arr, q_scale=10.):
    return (arr*q_scale).astype(np.int32)

def dequantize(arr, q_scale=10.):
    return arr / q_scale

@dataclass
class EncodingResult:
    encoded_bytes: bytes
    # This is the height of the DWT coefficients! Not the height of the
    # original image!
    h: int
    # This is the width of the DWT coefficients! Not the width of the
    # original image!
    w: int
    c: int
    max_n: int
    ll_h: int
    ll_w: int
    wavelet: str
    quantization_scale: float
    slices: List
    mode: str

    # the color_space (if any)
    # used to encode the image
    color_space: Optional[str] = None

    # This is an optional parameter that defines seperate quantization_scales
    # per channel
    # This is used for color spaces where some channels are more important than
    # others.
    per_channel_quant_scales: Optional[List[float]] = None


def encode_image(image: np.ndarray, wavelet='bior2.2', level=6, max_bits=None, quantization_scale=50, mode='reflect', color_space=None, per_channel_quant_scales=None):
    """
    Takes the DWT of the image, discretizes the DWT coeffs, and encodes it

    image: 3D ndarray of (C,H,W), containing floating point pixel values
    wavelet: type of pywt wavelet to use. The default is bior2.2 (also known as CDF 5/3).
    level: integer number of DWT levels. The default value of 6 works for
        images of greater than or 64x64 pixels.
    max_bits: max number of bits to use when encoding
    quantization_scale: the DWT coeffs are multiplied by this number before
        being encoded. The default value of 50 works with little perceptual loss
        for RGB pixels.

    Returns EncodingResult, which contains all of the values/settings needed
        for decoding
    """
    if image.ndim != 3:
        raise ValueError('image ndim must be 3: c,h,w')

    if color_space is not None:
        if color_space == 'ipt':
            image = rgb_to_ipt(image)
        else:
            raise ValueError(color_space)

    coeffs = pywt.wavedec2(image, wavelet=wavelet, level=level, mode=mode)
    ll_h, ll_w = coeffs[0].shape[1], coeffs[0].shape[2]
    coeffs_arr,slices = pywt.coeffs_to_array(coeffs, axes=(-2,-1))

    if per_channel_quant_scales is not None:
        channel_mults = np.array(per_channel_quant_scales)
        coeffs_arr = channel_mults[:,None,None] * coeffs_arr

    coeffs_arr = quantize(coeffs_arr, quantization_scale)

    c,h,w = coeffs_arr.shape

    if max_bits == None:
        # very large number
        max_bits = 99999999999999999

    encoded_bytes, max_n = spiht_rs.encode(coeffs_arr, ll_h, ll_w, max_bits)

    encoding_result = EncodingResult(
            encoded_bytes,
            h,
            w,
            c,
            max_n,
            ll_h,
            ll_w,
            wavelet,
            quantization_scale,
            slices,
            mode,
            color_space,
            per_channel_quant_scales
        )
    
    return encoding_result


def decode_image(encoding_result: EncodingResult) -> np.ndarray:
    """
    Decodes the encoding_result to pixel values
    """
    encoded_bytes = encoding_result.encoded_bytes
    h = encoding_result.h
    w = encoding_result.w
    c = encoding_result.c
    max_n = encoding_result.max_n
    ll_h = encoding_result.ll_h
    ll_w = encoding_result.ll_w
    wavelet = encoding_result.wavelet
    quantization_scale = encoding_result.quantization_scale
    slices=encoding_result.slices
    mode=encoding_result.mode
    color_space=encoding_result.color_space
    per_channel_quant_scales=encoding_result.per_channel_quant_scales

    rec_arr = spiht_rs.decode(encoded_bytes, max_n, c, h, w, ll_h, ll_w)

    if per_channel_quant_scales is not None:
        channel_mults = np.array(per_channel_quant_scales)
        rec_arr = rec_arr / channel_mults[:,None,None]

    rec_arr = dequantize(rec_arr, quantization_scale)
    rec_coeffs = pywt.array_to_coeffs(rec_arr, slices, output_format='wavedec2')
    rec_image = pywt.waverec2(rec_coeffs, wavelet, mode=mode)

    if color_space is not None:
        if color_space == 'ipt':
            rec_image = ipt_to_rgb(rec_image)
        else:
            raise ValueError(color_space)

    return rec_image
