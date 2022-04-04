import numpy as np


def _windowed_view(data, window_length, window_step):
    """Windower method which windows a given signal in to a given window size.
    Parameters
    ----------
    data : ndarray
        Data to be windowed. Shape: (n_channels, time)
    window_length : int
        Required window length in sample points.
    window_step : int
        Required window step in sample points.
    Returns
    -------
    ndarray
        Windowed data with shape (n_windows, n_channels, time)
    """
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
        x = _windowed_view(data[i, :, :], int(window_length * fs), int(window_step * fs))
        windowed_tasks.append(np.array(x))
    return np.array(windowed_tasks)


def filter_mne_obj(mne_obj, f_type='butter', order=5, l_freq=1, h_freq=None, n_jobs=1):
    mne_obj = mne_obj.copy()
    iir_params = dict(order=order, ftype=f_type, output='sos')
    mne_obj.filter(l_freq=l_freq, h_freq=h_freq, method='iir', iir_params=iir_params, skip_by_annotation='edge',
                   n_jobs=n_jobs)
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
