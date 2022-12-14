from enum import Enum, auto
from pathlib import Path

import mne
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.ensemble import VotingClassifier
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline, FeatureUnion
from sklearn.preprocessing import FunctionTransformer
from sklearn.preprocessing import LabelEncoder, StandardScaler, Normalizer, MinMaxScaler
from sklearn.svm import SVC

from ..ai.classifier import test_classifier
from ..artifact_filtering.faster import ArtefactFilter
from ..databases import Databases
from ..feature_extraction import to_micro_volt, FeatureType, eeg_bands
from ..feature_extraction.frequency.fft_methods import FFTCalc, AvgFFTCalc, get_fft_ranges
from ..preprocess.io import DataLoader, get_epochs_from_raw, SubjectHandle
from ..utils import window_epochs, filter_mne_obj, balance_epoch_nums, _create_binary_label, \
    standardize_eeg_channel_names


def new_multi_svm(fs, fft_ranges, *, method='psd2', norm=StandardScaler):
    inner_clfs = [(f'unit{i}', make_pipeline(AvgFFTCalc(fft_low, fft_high),
                                             norm(), SVC(probability=True)))
                  for i, (fft_low, fft_high) in enumerate(fft_ranges)]

    clf = make_pipeline(
        FunctionTransformer(to_micro_volt),
        FFTCalc(fs, method),
        VotingClassifier(inner_clfs, voting='soft', n_jobs=len(inner_clfs)) if len(inner_clfs) > 1 else inner_clfs[0][1]
    )

    return clf


def band_comb_svm(fs, fft_ranges, cache_size=2048):
    assert len(fft_ranges) == 1
    fft_low, fft_high = fft_ranges[0]

    normalizers = FeatureUnion([(norm.__name__, norm()) for norm in
                                [FunctionTransformer, Normalizer, MinMaxScaler, StandardScaler]])

    parallel_lines = [
        make_pipeline(FFTCalc(fs, meth), AvgFFTCalc(fft_low, fft_high), normalizers)
        for meth in ['psd', 'psd2', 'fftabs', 'fftpow']
    ]

    parallel_lines = [(f'feature{i}', pl) for i, pl in enumerate(parallel_lines)]

    clf = make_pipeline(
        FunctionTransformer(to_micro_volt),
        FeatureUnion(parallel_lines),
        PCA(n_components=63),
        SVC(cache_size=cache_size, probability=True)
    )
    return clf


def band_comb_multi_svm(fs, fft_ranges):
    inner_clfs = [(f'unit{i}', band_comb_svm(fs, [fft_bin]))
                  for i, fft_bin in enumerate(fft_ranges)]
    assert len(inner_clfs) % 2 == 1
    clf = make_pipeline(
        # FunctionTransformer(to_micro_volt),
        # FFTCalc(fs),
        VotingClassifier(inner_clfs, voting='soft', n_jobs=len(inner_clfs)) if len(inner_clfs) > 1 else inner_clfs[0][1]
    )

    return clf


def norm_test_svm(fs, *, norm=StandardScaler):
    fft_ranges = []
    for fft_par in eeg_bands.values():
        fft_ranges.extend(get_fft_ranges(**fft_par))
    fft_ranges = sorted(set(fft_ranges), key=lambda tup: tup[0])

    band_lines = FeatureUnion([(f'band {fft_low}-{fft_high}', AvgFFTCalc(fft_low, fft_high))
                               for fft_low, fft_high in fft_ranges])

    parallel_lines = [
        make_pipeline(FFTCalc(fs, meth), band_lines, norm())
        for meth in ['psd', 'psd2', 'fftabs', 'fftpow']
    ]

    parallel_lines = [(f'feature{i}', pl) for i, pl in enumerate(parallel_lines)]

    clf = make_pipeline(
        FunctionTransformer(to_micro_volt),
        FeatureUnion(parallel_lines),
        PCA(n_components=63),
        SVC(cache_size=2048)
    )

    return clf


def norm_test_multi_svm(fs, *, norm=StandardScaler):
    fft_ranges = []
    for fft_par in eeg_bands.values():
        fft_ranges.extend(get_fft_ranges(**fft_par))
    fft_ranges = sorted(set(fft_ranges), key=lambda tup: tup[0])

    def get_fft_bin(f_low, f_high):
        fft_bins = [(method, make_pipeline(FFTCalc(fs, method), AvgFFTCalc(f_low, f_high), norm()))
                    for method in ['psd', 'psd2', 'fftabs', 'fftpow']]
        return FeatureUnion(fft_bins)

    inner_clfs = [
        (f'unit{i}', make_pipeline(get_fft_bin(fft_low, fft_high), PCA(n_components=63), SVC(probability=True)))
        for i, (fft_low, fft_high) in enumerate(fft_ranges)]

    clf = make_pipeline(
        FunctionTransformer(to_micro_volt),
        VotingClassifier(inner_clfs, voting='soft', n_jobs=len(inner_clfs))
        # if len(inner_clfs) > 1 else inner_clfs[0][1]
    )

    return clf


def fft_test_svm(fs, method='psd2'):
    fft_ranges = []
    for fft_par in eeg_bands.values():
        fft_ranges.extend(get_fft_ranges(**fft_par))
    fft_ranges = sorted(set(fft_ranges), key=lambda tup: tup[0])

    normalizers = FeatureUnion([(norm.__name__, norm()) for norm in
                                [FunctionTransformer, Normalizer, MinMaxScaler, StandardScaler]])

    band_lines = FeatureUnion([(f'band {fft_low}-{fft_high}',
                                make_pipeline(AvgFFTCalc(fft_low, fft_high), normalizers))
                               for fft_low, fft_high in fft_ranges])

    clf = make_pipeline(
        FunctionTransformer(to_micro_volt),
        FFTCalc(fs, method),
        band_lines,
        PCA(n_components=63),
        SVC(cache_size=2048)
    )

    return clf


def fft_test_multi_svm(fs, method='psd2'):
    fft_ranges = []
    for fft_par in eeg_bands.values():
        fft_ranges.extend(get_fft_ranges(**fft_par))
    fft_ranges = sorted(set(fft_ranges), key=lambda tup: tup[0])

    normalizers = FeatureUnion([(norm.__name__, norm()) for norm in
                                [FunctionTransformer, Normalizer, MinMaxScaler, StandardScaler]])

    inner_clfs = [(f'unit{i}', make_pipeline(
        AvgFFTCalc(fft_low, fft_high), normalizers,
        PCA(n_components=63), SVC(probability=True))
                   ) for i, (fft_low, fft_high) in enumerate(fft_ranges)]

    clf = make_pipeline(
        FunctionTransformer(to_micro_volt),
        FFTCalc(fs, method),
        VotingClassifier(inner_clfs, voting='soft', n_jobs=len(inner_clfs))
        # if len(inner_clfs) > 1 else inner_clfs[0][1]
    )

    return clf


class TestType(Enum):
    NO_TEST = auto()
    BAND_COMB = auto()
    NORM_SINGLE = auto()
    NORM_MULTI = auto()
    FFT_SINGLE = auto()
    FFT_MULTI = auto()


TEST = TestType.NO_TEST


def get_classifier(fs, fft_ranges, norm, method):
    if TEST is TestType.NO_TEST:
        clf = new_multi_svm(fs, fft_ranges, method=method, norm=norm)
    elif TEST is TestType.BAND_COMB:
        clf = band_comb_multi_svm(fs, fft_ranges)
    elif TEST is TestType.NORM_SINGLE:
        clf = norm_test_svm(fs, norm=norm)
    elif TEST is TestType.NORM_MULTI:
        clf = norm_test_multi_svm(fs, norm=norm)
    elif TEST is TestType.FFT_SINGLE:
        clf = fft_test_svm(fs, method)
    elif TEST is TestType.FFT_MULTI:
        clf = fft_test_multi_svm(fs, method)

    else:
        raise NotImplementedError

    return clf


def train_test_model(x, y, groups, fs, fft_ranges, norm=StandardScaler, method='psd2'):
    label_encoder = LabelEncoder()
    y = label_encoder.fit_transform(y)
    kfold = StratifiedGroupKFold(shuffle=False)

    cross_acc = []
    for train, test in kfold.split(np.arange(len(x)), y, groups):
        train_x = x[train]
        train_y = y[train]
        test_x = x[test]
        test_y = y[test]

        clf = get_classifier(fs, fft_ranges, norm, method)
        clf.fit(train_x, train_y)
        acc = test_classifier(clf, test_x, test_y, label_encoder)

        cross_acc.append(acc)
    print("Accuracy scores for k-fold crossvalidation: {}\n".format(cross_acc))
    print(f"Avg accuracy: {np.mean(cross_acc):.4f}   +/- {np.std(cross_acc):.4f}")
    return cross_acc


def test_db(feature_params, db_name,
            epoch_tmin=0, epoch_tmax=4,
            window_length=2, window_step=.1,
            use_drop_subject_list=True,
            filter_params=None,
            do_artefact_rejection=True,
            balance_data=True,
            norm=StandardScaler,
            method='psd2',
            subj_cp=0,
            log_file='out.csv'):
    if filter_params is None:
        filter_params = {}
    loader = DataLoader('../..', use_drop_subject_list=use_drop_subject_list,
                        subject_handle=SubjectHandle.INDEPENDENT_DAYS)
    loader.use_db(db_name)
    res = {
        'Subject': [],
        'Accuracy list': [],
        'Std of Avg. Acc': [],
        'Avg. Acc': []
    }

    for subj in loader.get_subject_list():
        if subj < subj_cp:
            continue
        files = loader.get_filenames_for_subject(subj)
        task_dict = loader.get_task_dict()
        event_id = loader.get_event_id()
        print(f'\nSubject{subj}')
        raws = [mne.io.read_raw(file) for file in files]
        raw = mne.io.concatenate_raws(raws)
        raw.load_data()
        fs = raw.info['sfreq']

        standardize_eeg_channel_names(raw)
        try:  # check available channel positions
            mne.channels.make_eeg_layout(raw.info)
        except RuntimeError:  # if no channel positions are available create them from standard positions
            montage = mne.channels.make_standard_montage('standard_1005')  # 'standard_1020'
            raw.set_montage(montage, on_missing='warn')

        if len(filter_params) > 0:
            raw = filter_mne_obj(raw, **filter_params)

        epochs = get_epochs_from_raw(raw, task_dict,
                                     epoch_tmin=epoch_tmin, epoch_tmax=epoch_tmax,
                                     event_id=event_id)
        del raw

        if do_artefact_rejection:
            epochs = ArtefactFilter(apply_frequency_filter=False).offline_filter(epochs)

        ep_labels = [list(epochs[i].event_id)[0] for i in range(len(epochs))]

        if balance_data:
            epochs, ep_labels = balance_epoch_nums(epochs, ep_labels)

        if db_name is Databases.GAME_PAR_D:
            ep_labels = [_create_binary_label(label) for label in ep_labels]

        # window the epochs
        windowed_data = window_epochs(epochs.get_data(),
                                      window_length=window_length, window_step=window_step,
                                      fs=fs)
        del epochs

        groups = [i // windowed_data.shape[1] for i in range(windowed_data.shape[0] * windowed_data.shape[1])]
        labels = [ep_labels[i // windowed_data.shape[1]] for i in range(len(groups))]
        windowed_data = np.vstack(windowed_data)

        # features = FeatureExtractor(fs=fs, **feature_params).run(windowed_data)
        features = windowed_data
        fft_ranges = get_fft_ranges(**feature_params)

        print("####### Classification report for subject{}: #######".format(subj))
        cross_acc = train_test_model(features, labels, groups, fs, fft_ranges, norm, method)
        res['Subject'].append(subj)
        res['Accuracy list'].append(cross_acc)
        res['Std of Avg. Acc'].append(np.std(cross_acc))
        res['Avg. Acc'].append(np.mean(cross_acc))
        pd.DataFrame(res).to_csv(log_file, sep=';', encoding='utf-8', index=False)


def multi_svm_test(db_name):
    path = Path(db_name.name, 'multi')
    path.mkdir(parents=True, exist_ok=True)

    for band, feature_params in eeg_bands.items():
        test_db(
            feature_params=feature_params,
            db_name=db_name,
            filter_params=dict(  # required for FASTER artefact filter
                order=5, l_freq=1, h_freq=45
            ),
            do_artefact_rejection=True,
            log_file=str(path.joinpath(band + '_multi_svm.csv'))
        )


def band_comb_test(db_name):
    global TEST
    TEST = TestType.BAND_COMB

    path = Path(db_name.name, 'band')
    path.mkdir(parents=True, exist_ok=True)

    for band, feature_params in eeg_bands.items():
        test_db(
            feature_params=feature_params,
            db_name=db_name,
            filter_params=dict(  # required for FASTER artefact filter
                order=5, l_freq=1, h_freq=45
            ),
            do_artefact_rejection=True,
            log_file=str(path.joinpath(band + '_band_svm.csv'))
        )


def band_comb_test_old(db_name):
    global TEST
    TEST = TestType.NO_TEST

    path = Path(db_name.name, 'band_old')
    path.mkdir(parents=True, exist_ok=True)

    for band, feature_params in eeg_bands.items():
        test_db(
            feature_params=feature_params,
            db_name=db_name,
            filter_params=dict(  # required for FASTER artefact filter
                order=5, l_freq=1, h_freq=45
            ),
            norm=Normalizer,
            method='fftabs',
            do_artefact_rejection=True,
            log_file=str(path.joinpath(band + '_band_svm.csv'))
        )


def band_comb_test_old2(db_name, cp_subj=0):
    global TEST
    TEST = TestType.NO_TEST

    path = Path(db_name.name, 'band_old')
    path.mkdir(parents=True, exist_ok=True)

    for band, feature_params in eeg_bands.items():
        if band in ['gamma', 'range30', 'range40']:
            test_db(
                feature_params=feature_params,
                db_name=db_name,
                filter_params=dict(  # required for FASTER artefact filter
                    order=5, l_freq=1, h_freq=45
                ),
                norm=Normalizer,
                method='fftabs',
                do_artefact_rejection=True,
                subj_cp=cp_subj,
                log_file=str(path.joinpath(band + '_band_svm.csv'))
            )
            cp_subj = 0


def norm_test(db_name):
    global TEST

    path = Path(db_name.name, 'norm')
    path.mkdir(parents=True, exist_ok=True)

    for TEST in [TestType.NORM_SINGLE, TestType.NORM_MULTI]:

        for norm in [FunctionTransformer, Normalizer, StandardScaler, MinMaxScaler]:
            if norm is FunctionTransformer:
                log_file = 'no norm'
            elif norm is Normalizer:
                log_file = 'l2 norm'
            elif norm is StandardScaler:
                log_file = 'Standard Scale'
            elif norm is MinMaxScaler:
                log_file = 'MinMax Scale'
            else:
                raise ValueError

            test_db(
                feature_params=dict(  # this param is ignored but required
                    feature_type=FeatureType.AVG_FFT_POWER,
                    fft_low=14, fft_high=30
                ),
                db_name=db_name,
                filter_params=dict(  # required for FASTER artefact filter
                    order=5, l_freq=1, h_freq=45
                ),
                do_artefact_rejection=True,
                norm=norm,
                log_file=str(path.joinpath(f'{log_file}_{TEST.name}_svm.csv'))
            )


def fft_test(db_name):
    global TEST

    path = Path(db_name.name, 'base_feature')
    path.mkdir(parents=True, exist_ok=True)

    for TEST in [TestType.FFT_SINGLE, TestType.FFT_MULTI]:

        for method in ['psd', 'psd2', 'fftabs', 'fftpow']:
            test_db(
                feature_params=dict(  # this param is ignored but required
                    feature_type=FeatureType.AVG_FFT_POWER,
                    fft_low=14, fft_high=30
                ),
                db_name=db_name,
                filter_params=dict(  # required for FASTER artefact filter
                    order=5, l_freq=1, h_freq=45
                ),
                do_artefact_rejection=True,
                method=method,
                log_file=str(path.joinpath(f'{method}_{TEST.name}_svm.csv'))
            )


def make_tests_on(db_name=Databases.PHYSIONET):
    multi_svm_test(db_name)
    band_comb_test(db_name)
    norm_test(db_name)
    fft_test(db_name)


if __name__ == '__main__':
    band_comb_test_old2(Databases.PHYSIONET, 106)
    band_comb_test_old(Databases.GAME_PAR_D)
