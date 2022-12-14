import sys
from json import dump as json_dump, load as json_load
from multiprocessing import Queue, Process
from pathlib import Path
from pickle import dump as pkl_dump, load as pkl_load
from sys import platform

import numpy as np
from joblib.externals.loky import get_reusable_executor
from mne.io import read_raw

from .databases import REST, CALM, ACTIVE
from .handlers import select_folder_in_explorer

# config options
CONFIG_FILE = 'bionic_apps.cfg'
BASE_DIR = 'base_dir'


def window_data(data, window_length, window_step, fs):
    """Windower method which windows a given signal in to a given window size.

    Parameters
    ----------
    data : ndarray
        Data to be windowed. Shape: (n_channels, time)
    window_length : float
        Length of sliding window in seconds.
    window_step : float
        Step of sliding window in seconds.
    fs : int
        Sampling frequency.
    Returns
    -------
    ndarray
        Windowed data with shape (n_windows, n_channels, time)
    """
    window_length = int(window_length * fs)
    window_step = int(window_step * fs)
    if window_step > 0:
        overlap = window_length - window_step
        n_windows = data.shape[-1] - overlap
        assert n_windows > 0, f'Can not create {n_windows} windows.'
        new_shape = (n_windows // window_step, data.shape[0], window_length)
        new_strides = (window_step * data.strides[-1], *data.strides)
        result = np.lib.stride_tricks.as_strided(data, shape=new_shape, strides=new_strides)
    elif window_step == 0:
        result = data[..., :window_length]
        result = np.expand_dims(result, axis=0)
    else:
        raise ValueError(f'window_step parameter must be non negative. '
                         f'Got {window_step} instead.')
    return result


def window_epochs(data, window_length, window_step, fs):
    """Create sliding windowed data from epochs.

    Parameters
    ----------
    data : ndarray
        Epochs data with shape (n_epochs, n_channels, time)
    window_length : float
        Length of sliding window in seconds.
    window_step : float
        Step of sliding window in seconds.
    fs : int
        Sampling frequency.

    Returns
    -------
    ndarray
        Windowed epochs data with shape (n_epochs, n_windows, n_channels, time)
    """
    windowed_tasks = []
    for i in range(len(data)):
        x = window_data(data[i, :, :], window_length, window_step, fs)
        windowed_tasks.append(np.array(x))
    return np.array(windowed_tasks)


def filter_mne_obj(mne_obj, f_type='butter', order=5, l_freq=1, h_freq=None, picks=None, n_jobs=1):
    mne_obj = mne_obj.copy()
    iir_params = dict(order=order, ftype=f_type, output='sos')
    mne_obj.filter(l_freq=l_freq, h_freq=h_freq,
                   method='iir', iir_params=iir_params,
                   skip_by_annotation='edge',
                   picks=picks, n_jobs=n_jobs)
    return mne_obj


def balance_epoch_nums(epochs, labels, groups=None):
    labels = np.array(labels)
    class_xs = []
    min_elems = len(epochs)

    for label in np.unique(labels):
        lab_ind = (labels == label)
        class_xs.append((label, lab_ind))
        if np.sum(lab_ind) < min_elems:
            min_elems = np.sum(lab_ind)

    use_elems = min_elems

    sel_ind = list()
    for label, lab_ind in class_xs:
        ind = np.arange(len(labels))[lab_ind]
        if np.sum(lab_ind) > use_elems:
            np.random.shuffle(ind)
            ind = ind[:use_elems]
        sel_ind.extend(ind)

    sel_ind = np.sort(sel_ind)
    if groups is None:
        return epochs[sel_ind], labels[sel_ind]
    return epochs[sel_ind], labels[sel_ind], groups[sel_ind]


def is_platform(os_platform):
    if 'win' in os_platform:
        os_platform = 'win'
    return platform.startswith(os_platform)


def check_path_limit(path):
    assert len(path.name) < 255, f'Pathname exceeds 255 limit with {path.name} part.'
    if path.parent != path:
        check_path_limit(path.parent)


def load_pickle_data(filename):
    with open(str(filename), 'rb') as fin:
        data = pkl_load(fin)
    return data


def save_pickle_data(filename, data):
    with open(str(filename), 'wb') as f:
        pkl_dump(data, f)


def load_from_json(filename):
    with open(str(filename)) as json_file:
        data_dict = json_load(json_file)
    return data_dict


def save_to_json(filename, data_dict):
    with open(str(filename), 'w') as outfile:
        json_dump(data_dict, outfile, indent='\t')


def init_base_config(path='.'):
    """Loads base directory path from pickle data. If it does not exist it creates it.

    Parameters
    ----------
    path : str
        Relative path to search for config file.

    Returns
    -------
    str
        Base directory path.
    """
    file_dir = Path('.').resolve()
    file = file_dir.joinpath(path, CONFIG_FILE)
    try:
        cfg_dict = load_pickle_data(file)
        base_directory = cfg_dict[BASE_DIR]
    except FileNotFoundError:
        from .handlers.gui import select_base_dir
        base_directory = select_base_dir()
        cfg_dict = {BASE_DIR: base_directory}
        save_pickle_data(file, cfg_dict)
    return base_directory


def standardize_eeg_channel_names(raw):
    """Standardize channel positions and names.

    Specially designed for EEG channel standardization.
    source: mne.datasets.eegbci.standardize

    Parameters
    ----------
    raw : instance of Raw
        The raw data to standardize. Operates in-place.
    """
    rename = dict()
    for name in raw.ch_names:
        std_name = name.strip('.')
        std_name = std_name.upper()
        if std_name.endswith('Z'):
            std_name = std_name[:-1] + 'z'
        if 'FP' in std_name:
            std_name = std_name.replace('FP', 'Fp')
        if std_name.endswith('H'):
            std_name = std_name[:-1] + 'h'
        rename[name] = std_name
    raw.rename_channels(rename)


def _create_binary_label(label):
    if label != REST:
        label = CALM if CALM in label else ACTIVE
    return label


def mask_to_ind(mask):
    return np.arange(len(mask))[mask]


"""Helpers for memory management.

    Tensorflow does not free up GPU after training.
    Issue: https://github.com/tensorflow/tensorflow/issues/36465
"""


class _ExceptionWrapper:

    def __init__(self, ee):
        self.ee = ee
        __, __, self.tb = sys.exc_info()

    def re_raise(self):
        raise self.ee.with_traceback(self.tb)


def __wrapper_func(func, queue, *args, **kwargs):
    try:
        ans = func(*args, **kwargs)
    except Exception as e:
        ans = _ExceptionWrapper(e)
    queue.put(ans)


def process_run(func, args=(), kwargs=None, debug=False):
    """Helper function for memory usage management"""
    if kwargs is None:
        kwargs = {}
    if not debug:
        queue = Queue()
        p = Process(target=__wrapper_func, args=(func, queue) + args, kwargs=kwargs, daemon=True)
        p.start()
        ans = queue.get()
        p.join()
        if isinstance(ans, _ExceptionWrapper):
            ans.re_raise()
    else:
        ans = func(*args, **kwargs)
    return ans


def cleanup_after(func):
    """Clean up unused processes after using joblib library

    Joblib does not release processes to speed up re-usage of processes
    Issue: https://github.com/joblib/joblib/issues/945
    """

    def wrap(*args, **kwargs):
        ans = func(*args, **kwargs)
        get_reusable_executor().shutdown(wait=True)  # , kill_workers=True)
        return ans

    return wrap


def check_label_nums(limit=5, ignore=('Rest', 'Idle')):
    folder = select_folder_in_explorer('Select folder for label check!',
                                       'Label check')
    file_type = input('Type search pattern: ')
    path = Path(folder)
    for i, files in enumerate(path.rglob(f'*{file_type}')):
        raw = read_raw(files)
        labels = raw.annotations.description
        label_limit = [np.sum(label == labels) < limit for label in np.unique(labels) if label not in ignore]
        if any(label_limit):
            print(f'\nSome of the labels for subject{i} does not reach the minimum label limit.\n')
