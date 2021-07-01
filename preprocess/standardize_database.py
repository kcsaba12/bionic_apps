from pathlib import Path

import mne
import numpy as np
from matplotlib import pyplot as plt
from mne.externals.pymatreader import read_mat

from config import Physionet, IMAGINED_MOVEMENT, BOTH_LEGS
from gui_handler import select_folder_in_explorer
from preprocess import DataLoader, Databases


def get_filenames_from_dir(ext):
    ext = ext if ext[0] == '.' else '.' + ext
    path = Path(select_folder_in_explorer('Select base folder which contains the {} files'.format(ext),
                                          'Select directory'))
    filenames = list(path.rglob('*{}'.format(ext)))
    return filenames


def _save_sessions(subj, raw, start_mask, end_mask, path, session_num=13, drop_first=3, after_end=1.,
                   plot=False):
    start_ind = np.arange(len(start_mask))[start_mask]
    end_ind = np.arange(len(end_mask))[end_mask]
    assert len(start_ind) == session_num, f'Incorrect start Triggers at subject {subj}'
    assert len(end_ind) == session_num, f'Incorrect end Triggers at subject {subj}'

    # remove first 3 True from start mask -- eye, train1, train2 sessions
    start_mask[start_ind[:drop_first]] = False
    end_mask[end_ind[:drop_first]] = False

    tmins = raw.annotations.onset[start_mask]
    tmaxs = raw.annotations.onset[end_mask]
    for i, tmin in enumerate(tmins):
        tmax = tmaxs[i]
        sess = raw.copy()
        if i < len(tmins) - 1:
            sess.crop(tmin, tmax + 1)
        else:
            sess.crop(tmin, tmax + after_end)

        file = path.joinpath('S{:03d}'.format(subj), 'S{:03d}R{:02d}_raw.fif'.format(subj, i + 1))
        file.parent.mkdir(parents=True, exist_ok=True)
        sess.save(str(file), overwrite=True)

        if plot:
            sess.plot(block=False)

    if plot:
        raw.plot(block=False)
        plt.show()


def _add_missing_bci_comp_4_2_triggers(filename, raw):
    matfile = str(filename.with_suffix('.mat'))
    mat = read_mat(matfile)
    new_tiggers = mat['classlabel']
    tgdict = {i + 1: str(tg) for i, tg in enumerate([769, 770, 771, 772])}
    new_tiggers = list(map(lambda x: tgdict[x], new_tiggers))
    raw.annotations.description[raw.annotations.description == '783'] = new_tiggers


def convert_bcicompIV2a():
    loader = DataLoader('..').use_bci_comp_4_2a()
    path = loader.get_data_path()
    files = sorted(path.rglob('*{}'.format('.gdf')), key=lambda x: x.stem[-1], reverse=True)
    files = sorted(files, key=lambda x: x.stem[:-1])
    for subj, filename in enumerate(files):
        subj += 1
        raw = mne.io.read_raw(filename, preload=True, eog=(-3, -2, -1))  # eog channel index

        # correcting eeg channel names
        raw.rename_channels(lambda x: x.strip('EEG-'))
        new_map = {str(i): ch for i, ch in enumerate(['Fc3', 'Fc1', 'FCz', 'Fc2', 'Fc4', 'C5', 'C1', 'C2', 'C6',
                                                      'Cp3', 'Cp1', 'CPz', 'Cp2', 'Cp4', 'P1', 'P2', 'POz'])}
        raw.rename_channels(new_map)

        if filename.stem[-1] == 'E':  # adding correct trigger numbers ot evalset
            _add_missing_bci_comp_4_2_triggers(filename, raw)
        elif filename.stem[-1] == 'T':
            pass
        else:
            raise NotImplementedError

        # Session end trigger is missing, creating end mask from start_mask
        start_mask = raw.annotations.description == '32766'
        end_mask = start_mask.copy()
        end_mask[0] = False
        end_mask[-1] = True
        if subj == 7:
            drop_first = 1
        else:
            drop_first = 3
        session_num = 6 + drop_first
        _save_sessions(subj, raw, start_mask, end_mask, path, session_num=session_num, drop_first=drop_first,
                       after_end=5.7)


def convert_bcicompIV2b():
    loader = DataLoader('..', use_drop_subject_list=False).use_bci_comp_4_2b()
    path = loader.get_data_path()
    files = sorted(path.rglob('*{}'.format('.gdf')))
    for i, filename in enumerate(files):
        subj = i + 1
        raw = mne.io.read_raw(filename, preload=True, eog=(-3, -2, -1))  # eog channel index
        raw.rename_channels(lambda x: x.strip('EEG:'))
        if i % 5 < 3:
            pass
        else:
            _add_missing_bci_comp_4_2_triggers(filename, raw)

        # Session end trigger is missing, creating end mask from start_mask
        start_mask = raw.annotations.description == '32766'
        end_mask = start_mask.copy()
        end_mask[0] = False
        end_mask[-1] = True
        print(subj, filename)

        if subj in [2, 24]:
            drop_first = 0
        else:
            drop_first = 1

        if subj in [17, 22]:
            session_num = 7 + drop_first
        elif subj == 9:
            session_num = 3 + drop_first
        elif subj == 36:
            session_num = 8 + drop_first
        elif i % 5 < 2:
            session_num = 6 + drop_first
        else:
            session_num = 4 + drop_first
        _save_sessions(subj, raw, start_mask, end_mask, path, session_num=session_num, drop_first=drop_first,
                       after_end=5.7)


def _create_raw(eeg, ch_names, ch_types, fs, onset, duration, description):
    info = mne.create_info(ch_names, ch_types=ch_types, sfreq=fs)
    raw = mne.io.RawArray(eeg, info)
    annotation = mne.Annotations(onset, duration, description)
    raw = raw.set_annotations(annotation)
    return raw


def convert_bcicompIV1():
    filenames = get_filenames_from_dir('.mat')
    for i, file in enumerate(filenames):
        mat = read_mat(str(file))

        eeg = mat['cnt'].transpose().astype('double') * 1e-7  # convert to 1 Volt unit
        ch_names = mat['nfo']['clab']
        ch_types = ['eeg'] * len(ch_names)
        fs = mat['nfo']['fs']
        classes = mat['nfo']['classes']
        onset = mat['mrk']['pos'] / fs
        duration = [4] * len(onset)
        description = mat['mrk']['y']

        description = description.astype(object)
        description[description == 1] = classes[0]
        description[description == -1] = classes[1]
        filename = file.parent.joinpath('calib_ds_subj{:02d}_raw.fif'.format(i + 1))

        raw = _create_raw(eeg, ch_names, ch_types, fs, onset, duration, description)
        raw.save(str(filename), overwrite=True)


def convert_giga():
    filenames = get_filenames_from_dir('.mat')
    for file in filenames:
        mat = read_mat(str(file))
        raw_list = list()
        for state in ['EEG_MI_train', 'EEG_MI_test']:
            data_dict = mat[state]
            eeg = data_dict['x'].transpose() * 1e-6  # todo: waiting for info! convert to 1 Volt unit
            ch_names = data_dict['chan']
            ch_types = ['eeg'] * len(ch_names)
            fs = data_dict['fs']
            onset = data_dict['t'] / fs
            duration = [4] * len(onset)
            description = data_dict['y_class']

            raw_list.append(_create_raw(eeg, ch_names, ch_types, fs, onset, duration, description))

        raw = mne.concatenate_raws(raw_list)  # todo: same experiment?

        filename = str(file).strip('.mat') + '_raw.fif'
        # filename = file.parent.joinpath('calib_ds_subj{:02d}_raw.fif'.format(i + 1))
        raw.save(str(filename), overwrite=True)


def convert_physionet():
    loader = DataLoader('..', use_drop_subject_list=False).use_physionet()
    assert loader._db_type.CONFIG_VER == 0, 'File conversion only avaliable for CONFIG_VER=0'
    for s in range(Physionet.SUBJECT_NUM):
        subj = s + 1
        rec_nums = Physionet.TYPE_TO_REC[IMAGINED_MOVEMENT]
        raw_list = list()
        new_rec_num = 1
        for rec in rec_nums:
            filename = next(
                loader._generate_physionet_filenames(subj, rec)
            )
            trigger_id = Physionet.TRIGGER_CONV_REC_TO_TASK[rec]
            raw = mne.io.read_raw(filename, preload=True)
            if BOTH_LEGS in trigger_id:
                description = list()
                for t in raw.annotations.description:
                    if t == 'T0':
                        description.append(t)
                    elif t == 'T1':
                        description.append('T3')
                    elif t == 'T2':
                        description.append('T4')
                    else:
                        raise ValueError(f'{t} is not supported...')
                raw.annotations.description = description
            raw_list.append(raw)

            if len(raw_list) == 2:
                raw = mne.io.concatenate_raws(raw_list)
                raw_list = list()
                file = loader.get_data_path().joinpath('S{:03d}'.format(subj),
                                                       'S{:03d}R{:02d}_raw.fif'.format(subj, new_rec_num))
                file.parent.mkdir(parents=True, exist_ok=True)
                new_rec_num += 1
                raw.save(str(file), overwrite=True)


def convert_ttk():
    loader = DataLoader('..', use_drop_subject_list=True).use_ttk_db()
    assert loader._db_type.CONFIG_VER == 0, 'File conversion only avaliable for CONFIG_VER=0'

    for subj in loader.get_subject_list():
        filename = loader.get_filenames_for_subject(subj)[0]
        raw = mne.io.read_raw(filename, preload=True)

        start_mask = (raw.annotations.description == 'Response/R  1') | (raw.annotations.description == 'Stimulus/S 16')
        end_mask = raw.annotations.description == 'Stimulus/S 12'
        start_ind = np.arange(len(start_mask))[start_mask]
        end_ind = np.arange(len(end_mask))[end_mask]
        trigger_num = 13

        if subj == 2:
            # Session end trigger is missing, creating end mask from start_mask
            end_mask = np.array([False] * len(start_mask))
            ind = start_ind[1:] - 1
            end_mask[ind] = True
            end_mask[-1] = True
        elif subj == 12:
            # One extra start trigger at the end of the record...
            start_mask[start_ind[-1]] = False
        elif subj == 13:
            # 12 sessions instead of 10
            trigger_num += 2
        elif subj == 18:
            start_mask[start_ind[:2]] = False  # wrong trigger
            start_mask[start_ind[-2]] = False  # wrong trigger
            start_mask[start_ind[-3]] = False  # wrong session, with no end...
            end_mask[end_ind[0]] = False

        _save_sessions(subj, raw, start_mask, end_mask, loader.get_data_path(), trigger_num)


def convert_bad_ttk():
    loader = DataLoader('..', use_drop_subject_list=False).use_ttk_db()
    assert loader._db_type.CONFIG_VER == 0, 'File conversion only avaliable for CONFIG_VER=0'

    for subj in [1, 9, 17]:
        if subj == 1:
            filenames = loader._generate_ttk_filename(subj, [1, 2, 3])
        elif subj == 9:
            # rec02.vhdr file is corrupted...
            filenames = loader._generate_ttk_filename(subj, [1])
        else:
            filenames = loader._generate_ttk_filename(subj, [1, 2])

        raw = mne.io.concatenate_raws([mne.io.read_raw(file) for file in filenames])

        start_mask = (raw.annotations.description == 'Response/R  1') | (raw.annotations.description == 'Stimulus/S 16')
        end_mask = raw.annotations.description == 'Stimulus/S 12'
        start_ind = np.arange(len(start_mask))[start_mask]
        trigger_num = 13

        if subj == 1:
            start_mask[start_ind[8]] = False  # wrong start...
            start_ind = np.arange(len(start_mask))[start_mask]
            # Session end trigger is missing, creating end mask from start_mask
            end_mask = np.array([False] * len(start_mask))
            ind = start_ind[1:] - 1
            end_mask[ind] = True
            end_mask[-1] = True
        elif subj == 9:
            start_mask[start_ind[-1]] = False  # wrong start...
            trigger_num = 9
        elif subj == 17:
            end_ind = np.arange(len(end_mask))[end_mask]
            start_mask[start_ind[5]] = False  # wrong session
            end_mask[end_ind[5]] = False  # wrong session
            trigger_num = 12

        _save_sessions(subj, raw, start_mask, end_mask, loader.get_data_path(), trigger_num)


def convert_all_ttk():
    convert_ttk()
    convert_bad_ttk()


def convert_pilot_par_a_and_b():
    db_list = [Databases.PILOT_PAR_A, Databases.PILOT_PAR_B]
    for db_name in db_list:
        loader = DataLoader('..', use_drop_subject_list=True).use_db(db_name)
        assert loader._db_type.CONFIG_VER == 0, 'File conversion only avaliable for CONFIG_VER=0'

        for subj in loader.get_subject_list():
            filename = loader.get_filenames_for_subject(subj)[0]
            raw = mne.io.read_raw(filename, preload=True)
            start_mask = (raw.annotations.description == 'Response/R  1') | (
                    raw.annotations.description == 'Stimulus/S 16')
            end_mask = raw.annotations.description == 'Stimulus/S 12'
            _save_sessions(subj, raw, start_mask, end_mask, loader.get_data_path())


def convert_game_par_c_and_d():
    db_list = [Databases.GAME_PAR_C, Databases.GAME_PAR_D]
    for db_name in db_list:
        loader = DataLoader('..', use_drop_subject_list=True).use_db(db_name)
        assert loader._db_type.CONFIG_VER == 0, 'File conversion only avaliable for CONFIG_VER=0'

        for subj in loader.get_subject_list():
            filename = loader.get_filenames_for_subject(subj)[0]
            raw = mne.io.read_raw(filename, preload=True)
            start_mask = (raw.annotations.description == 'Response/R  1') | (
                    raw.annotations.description == 'Stimulus/S 16')
            end_mask = raw.annotations.description == 'Stimulus/S 12'
            drop_first = 1
            session_num = drop_first + 5
            _save_sessions(subj, raw, start_mask, end_mask, loader.get_data_path(), session_num, drop_first,
                           plot=True)


if __name__ == '__main__':
    convert_game_par_c_and_d()
