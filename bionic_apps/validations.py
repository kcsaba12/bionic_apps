from .ai.classifier import ClassifierType
from .feature_extraction import FeatureType


def validate_feature_classifier_pair(feature_type, classifier_type):
    if classifier_type is ClassifierType.EEG_NET:
        feature_type = FeatureType.RAW
    elif classifier_type is ClassifierType.VOTING_SVM and \
            feature_type in [FeatureType.AVG_FFT_POWER, FeatureType.FFT_RANGE, FeatureType.MULTI_AVG_FFT_POW]:
        pass
    else:
        raise ValueError(f'Feature {feature_type.name} and classifier {classifier_type.name} '
                         f'can not be used together.')

    return feature_type, classifier_type
