from enum import Enum

from mne.decoding import Scaler
from sklearn.base import TransformerMixin
from sklearn.pipeline import FeatureUnion, make_pipeline, Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

from .frequency.fft_methods import get_multi_fft_transformer, get_fft_ranges
from .time.utils import *


class FeatureType(Enum):
    RAW = 'raw'
    USER_PIPELINE = 'user'

    # time domain:
    HUGINES = 'hugines'

    # feq domain:
    AVG_FFT_POWER = 'avg_fft_pow'
    FFT_RANGE = 'fft_range'
    MULTI_AVG_FFT_POW = 'multi_avg_fft_pow'


eeg_bands = {
    'theta': dict(
        feature_type=FeatureType.AVG_FFT_POWER,
        fft_low=4, fft_high=7
    ),
    'alpha': dict(
        feature_type=FeatureType.AVG_FFT_POWER,
        fft_low=7, fft_high=14
    ),
    'beta': dict(
        feature_type=FeatureType.AVG_FFT_POWER,
        fft_low=14, fft_high=30
    ),
    'gamma': dict(
        feature_type=FeatureType.AVG_FFT_POWER,
        fft_low=30, fft_high=40
    ),
    'range30': dict(
        feature_type=FeatureType.FFT_RANGE,
        fft_low=4, fft_high=30
    ),
    'range40': dict(
        feature_type=FeatureType.FFT_RANGE,
        fft_low=2, fft_high=40
    ),
}


def to_micro_volt(data):
    return data * 1e6


def get_hugines_transfromer():
    features = [wave_len, zero_crossings, slope_sign_change, RMS]
    return FeatureUnion([(fun.__name__, FunctionTransformer(fun)) for fun in features])


def get_feature_extractor(feature_type, fs=None, scale=True, norm=False, info=None, **kwargs):
    pipeline_steps = []
    if scale:
        pipeline_steps.append(FunctionTransformer(to_micro_volt))

    if feature_type is FeatureType.RAW:
        pipeline_steps.append(FunctionTransformer())
        norm = info is not None and norm
    elif feature_type is FeatureType.HUGINES:
        pipeline_steps.append(get_hugines_transfromer())
    elif feature_type in [FeatureType.AVG_FFT_POWER, FeatureType.FFT_RANGE, FeatureType.MULTI_AVG_FFT_POW]:
        assert isinstance(fs, (int, float)), 'Sampling frequency must be defined!'
        pipeline_steps.append(get_multi_fft_transformer(feature_type, fs, **kwargs))
    else:
        raise NotImplementedError(f'{feature_type.name} feature extraction is not implemented.')

    if norm:
        if feature_type is FeatureType.RAW:
            scaler = Scaler(info, scalings='mean')
        else:
            scaler = StandardScaler()
        pipeline_steps.append(scaler)

    return make_pipeline(*pipeline_steps)


def generate_features(x, fs=None, f_type=FeatureType.RAW, scale=True, norm=False,
                      info=None, pipeline=None, **kwargs):
    if f_type is FeatureType.USER_PIPELINE:
        assert isinstance(pipeline, (Pipeline, FeatureUnion, TransformerMixin)), \
            f'In case of user defined feature extractor only sklearn transformers accepted.'
        feature_ext = pipeline
    else:
        feature_ext = get_feature_extractor(f_type, fs, scale, norm, info=info, **kwargs)
    x = feature_ext.fit_transform(x)
    return x
