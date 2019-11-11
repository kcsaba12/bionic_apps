import mne
import numpy as np
from matplotlib import pyplot as plt
from preprocess.ioprocess import OfflineDataPreprocessor, get_record_number, open_raw_file


def plot_avg(epochs):
    """
    Creates average plots from epochs
    :param epochs: eeg epoch, mne class
    """
    ev_left = epochs['left hand'].average()
    ev_right = epochs['right hand'].average()
    ev_rest = epochs['rest'].average()

    f, axs = plt.subplots(1, 3, figsize=(10, 5))
    _ = f.suptitle('Left / Right hand', fontsize=20)
    _ = ev_left.plot(axes=axs[0], show=False, time_unit='s')
    _ = ev_right.plot(axes=axs[1], show=False, time_unit='s')
    _ = ev_rest.plot(axes=axs[2], show=False, time_unit='s')
    plt.tight_layout()


def plot_topo_psd(epochs, layout=None, bands=None, title=None, dB=True):
    """
    Creates topographical psd map
    :param epochs: eeg data
    :param layout: channels in space
    :param bands: eeg bands with given range
    :param title: title of plot
    :param dB: logarithmic plot
    """
    if bands is None:
        bands = [(0, 4, 'Delta'), (4, 8, 'Theta'), (8, 12, 'Alpha'), (12, 30, 'Beta'), (30, 45, 'Gamma')]
    if title is not None:
        bands = [(frm, to, name + ' ' + title) for frm, to, name in bands]

    epochs.plot_psd_topomap(bands=bands, layout=layout, dB=dB, show=False)


def plot_projs_topomap(epoch, ch_type='eeg', layout=None, title=None):
    fig = epoch.plot_projs_topomap(ch_type=ch_type, layout=layout)
    if title:
        fig.title(title)


def plot_csp(epoch, layout=None, n_components=4, title=None):
    """
    Common spacial patterns in topographical map
    :param epoch: eeg data
    :param layout: channels in space
    :param n_components: number or CSP components
    :param title: figure title
    """
    labels = epoch.events[:, -1] - 1
    data = epoch.get_data()

    csp = mne.decoding.CSP(n_components=n_components)
    csp.fit_transform(data, labels)
    csp.plot_patterns(epoch.info, layout=layout, ch_type='eeg', show=False, title=title)


def filter_raw_butter(raw, l_freq=7, h_freq=30, order=5, show=False):
    """
    Creating butterworth bandpass filter with MNE and visualise the power spectral density
    :param raw: eeg file
    :param l_freq: low freq
    :param h_freq: high freq
    :param order: filter order
    :param show: to plot immediately
    """
    # sos = signal.iirfilter(order, (lowf, highf), btype='bandpass', ftype='butter', output='sos', fs=raw.info['sfreq'])
    iir_params = dict(order=order, ftype='butter', output='sos')
    raw.filter(l_freq=l_freq, h_freq=h_freq, method='iir', iir_params=iir_params)

    if show:
        raw.plot()
        raw.plot_psd()


def ica_artefact_correction(eeg, layout=None, title=None):
    """
    Creating ICA components
    todo: continue to eye artefact correction
    :param eeg: raw or epoch
    :param layout: channels in space
    :param title: plot title
    """
    picks = mne.pick_types(eeg.info, meg=False, eeg=True, stim=False, eog=False, exclude='bads')

    ica_method = 'fastica'
    n_components = 20
    decim = 3
    random_state = 12

    ica = mne.preprocessing.ICA(n_components=n_components, method=ica_method, random_state=random_state, max_iter=1000)

    reject = dict(mag=5e-12, grad=4000e-13, eeg=40e-6)  # todo: threshold???

    ica.fit(eeg, picks=picks, decim=decim, reject=reject)
    ica.plot_components(layout=layout, title=title, show=False)


def wavelet_time_freq(epochs, n_cycles=5, l_freq=7, h_freq=30, f_step=0.5, average=True, channels=None, title=None):
    """
    Spatial-frequency analysis by using morlet wavelet
    :param epochs: eeg data
    :param n_cycles: iteration
    :param l_freq: lowest freq
    :param h_freq: highest freq
    :param f_step: step between frequencies
    :param average: to average epoch data
    :param channels: plot for specific channels
    :param title: plot title
    """
    freqs = np.arange(l_freq, h_freq, f_step)

    if channels is None:
        channels = epochs.info['ch_names']
        channels = channels[:-1]

    if average:
        power, itc = mne.time_frequency.tfr_morlet(epochs, freqs=freqs, n_cycles=n_cycles, return_itc=True, decim=3,
                                                   n_jobs=1)
    else:
        power = mne.time_frequency.tfr_morlet(epochs, freqs=freqs, n_cycles=n_cycles, return_itc=False, decim=3,
                                              n_jobs=1, average=False)

    indices = [power.ch_names.index(ch_name) for ch_name in channels]
    for i, ind in enumerate(indices):
        power.plot(picks=[ind], show=False, title=title + ' ' + channels[i])


def design_filter(fs=1000, lowf=7, highf=30, order=5):
    """
    Bandpass filter design and plot function
    :param fs: sampling freq
    :param lowf: low freq
    :param highf: high freq
    :param order: filter order
    """
    from scipy import signal

    flim = (1., fs / 2.)

    freq = [0., lowf, highf, fs / 2.]
    gain = [0., 1., 1., 0.]

    sos = signal.iirfilter(order, (lowf, highf), btype='bandpass', ftype='butter', output='sos', fs=fs)
    mne.viz.plot_filter(dict(sos=sos), fs, freq, gain, 'Butterworth: order={}, fs={}'.format(order, fs),
                        flim=flim)


def test_plot_topomap(epochs, layout, ch_type='eeg', crop=True):
    """
    This is an example function about how to get topographically represented data from mne
    The data is NOT a picture the data is a matrix!

    Use only the required parts!!!
    """
    from mne.channels import _get_ch_type
    from mne.viz.topomap import _prepare_topo_plot

    # to get pos data from layout
    ch_type = _get_ch_type(epochs, ch_type)
    picks, pos, merge_grads, names, ch_type = _prepare_topo_plot(
        epochs, ch_type, layout)

    data3d = epochs.get_data()

    # this only works if [:2] removed from  the return of plot_topomap. Catch interp!!!
    # we are setting the first data in here...
    im, _, interp = mne.viz.plot_topomap(data3d[1, :, 110], pos, show=False)

    # getting spatially represented eeg signals aka spatial transformation. res: 64 x 64 data
    # interp.set_values(data)  # we could reuse the interpolator
    spatial_data = interp()

    # removing data from the border - ROUND electrode system
    if crop:
        r = np.size(spatial_data, axis=0) / 2
        for i in range(int(2 * r)):
            for j in range(int(2 * r)):
                if np.power(i - r, 2) + np.power(j - r, 2) > np.power(r, 2):
                    spatial_data[i, j] = 0

    plt.figure()
    plt.imshow(np.flipud(spatial_data))
    plt.show()


def filter_on_file(filename, proc, tmin=0, tmax=4, ref_channels=None):
    """
    Makes feature extraction methods on given file
    Select feature extreaction method in for cycle.
    Only for demonstration purpose...
    """
    raw = open_raw_file(filename)

    """MUST HAVE!!! Otherwise error!"""
    raw.rename_channels(lambda x: x.strip('.'))

    if ref_channels is not None:
        raw.set_eeg_reference(ref_channels=ref_channels)

    rec_num = get_record_number(filename)
    task_dict = proc.convert_task(rec_num)
    layout = mne.channels.read_layout('EEG1005')

    # raw_alpha = raw.copy()
    # raw_beta = raw.copy()
    # raw_alpha = raw_alpha.filter(7, 13)
    # raw_beta = raw_beta.filter(14, 30)

    events, _ = mne.events_from_annotations(raw, event_id=proc.get_trigger_event_id())

    epochs = mne.Epochs(raw, events, event_id=task_dict, tmin=tmin, tmax=tmax, preload=True)
    # epoch_alpha = mne.Epochs(raw_alpha, events, event_id=task_dict, tmin=tmin, tmax=tmax, preload=True)
    # epoch_beta = mne.Epochs(raw_beta, events, event_id=task_dict, tmin=tmin, tmax=tmax, preload=True)

    test_plot_topomap(epochs, layout)

    filter_raw_butter(raw)
    bands = [(i, i + 2, '{}-{} Hz'.format(i, i + 2)) for i in range(0, 40, 2)]

    from config import EYE_OPEN, EYE_CLOSED
    n_ = min([len(epochs[task]) for task in task_dict if task != EYE_OPEN and task != EYE_CLOSED])
    n_ = 5
    fignum = 1
    for i in range(n_):
        for task in task_dict:
            ep = epochs[task]
            if i < len(ep):
                # wavelet_time_freq(ep[i], channels=['Cz', 'C3', 'C4'], title=task+str(i))
                plot_topo_psd(ep[i], layout, title=task + str(i), bands=bands)
                # plot_projs_topomap(epochs[task], layout=layout, title=task)
                # ica_artefact_correction(ep, layout=layout, title=task + str(i))

                # plt.savefig('fig{}.png'.format(fignum), format='png')
                fignum += 1

    # epoch_alpha['left hand'].plot(n_channels=len(raw.info['ch_names']) - 1, events=events, block=True)

    # plot_avg(epoch_alpha)

    # # CSP
    # n_comp = 4
    # plot_csp(epoch_alpha, layout, n_components=n_comp, title='alpha range')
    # plot_csp(epoch_beta, layout, n_components=n_comp, title='beta range')

    plt.show()


if __name__ == '__main__':
    base_dir = "D:/BCI_stuff/databases/"  # MTA TTK
    # base_dir = 'D:/Csabi/'  # Home
    # base_dir = "D:/Users/Csabi/data/"  # ITK
    # base_dir = "/home/csabi/databases/"  # linux

    proc = OfflineDataPreprocessor(base_dir)

    subj = 2
    rec = 8

    db = 'pilot'  # 'physionet

    if db == 'pilot':
        file = '{}Cybathlon pilot/pilot{}/rec01.vhdr'.format(base_dir, subj)
        proc.use_pilot()
        filter_on_file(file, proc, ref_channels=['TP9', 'TP10'])
    else:  # physionet
        file = '{}physionet.org/physiobank/database/eegmmidb/S{:03d}/S{:03d}R{:02d}.edf'.format(base_dir, subj, subj,
                                                                                                rec)
        proc.use_physionet()
        filter_on_file(file, proc)