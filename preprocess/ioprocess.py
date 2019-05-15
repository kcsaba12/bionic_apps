import numpy as np
import mne
from config import *

EPOCH_DB = 'preprocessed_database'


def open_raw_file(filename, preload=True, stim_channel='auto'):
    ext = filename.split('.')[-1]

    switcher = {
        'edf': mne.io.read_raw_edf,
        'eeg': mne.io.read_raw_brainvision,  # todo: check...
    }
    # Get the function from switcher dictionary
    mne_io_read_raw = switcher.get(ext, lambda: "nothing")
    # Execute the function
    return mne_io_read_raw(filename, preload=preload, stim_channel=stim_channel)


class EEGFileHandler:

    def __init__(self, filename):
        self._filename = filename
        self._file_handler = open_raw_file(filename)
        self._tmin = 0  # beggining of raw, In seconds!!! use fs!
        self._tmax = None
        # self._epoch_index = None
        # self._epoch_dict = None

    def open_file(self):
        raw = open_raw_file(self._filename)
        self._file_handler = raw.crop(self._tmin, self._tmax)

    def create_epochs(self, epoch_dict=None, tmin=0, tmax=4, preload=False):
        # self._epoch_dict = epoch_dict
        # self._tmin = tmin
        # self._tmax = tmax
        events = mne.find_events(self._file_handler, shortest_event=0, stim_channel='STI 014', initial_event=True,
                                 consecutive=True)
        epochs = mne.Epochs(self._file_handler, events, event_id=epoch_dict, tmin=tmin, tmax=tmax,
                            proj=True, baseline=None, preload=preload)


class OfflineEpochCreator:
    """
    Preprocessor for edf files. Creates a database, which has all the required information about the eeg files.
    """

    def __init__(self, base_dir, use_drop_subject_list=True):
        self._base_dir = base_dir
        self._data_path = None
        self._data_duration = 4  # seconds
        self._db_type = None

        # self._db_ext = None
        # self._trigger_task_list = None

        self._drop_subject = set()
        if use_drop_subject_list:
            self._drop_subject.add(-1)

        if not base_dir[-1] == '/':
            self._base_dir = base_dir + '/'

    def _use_db(self, db_type):
        """
        Loads a specified database.

        :param path: where the database is available
        """
        self._data_path = self._base_dir + db_type.DIR
        self._db_type = db_type
        self._drop_subject = db_type.DROP_SUBJECTS

    def use_physionet(self):
        self._use_db(Physionet)
        return self

    @property
    def _db_ext(self):
        return self._db_type.DB_EXT

    @property
    def _trigger_task_list(self):
        return self._db_type.TRIGGER_TASK_LIST

    def _conv_type(self, record_num):
        return self._db_type.TRIGGER_TYPE_CONVERTER.get(record_num)

    def _conv_task(self, record_num, task_ID):
        return self._db_type.TRIGGER_TASK_CONVERTER.get(record_num).get(task_ID)

    @staticmethod
    def get_filenames_in(path, ext='', recursive=True):
        """
        Searches for files in the given path with specified extension

        :param path: path where to do the search
        :param ext: file extension to search for
        :return: list of filenames
        :raises FileNotFoundError if no files were found
        """
        import glob
        if ext is None:
            ext = ''
        files = glob.glob(path + '/**/*' + ext, recursive=recursive)
        if not files:
            raise FileNotFoundError('Files are not available in path: {}'.format(path))
        return files

    def run(self):
        self._create_epochs_from_db()

    """
    Database functions
    """

    def _get_filenames(self):
        return self.get_filenames_in(self._data_path, self._db_ext)

    def _open_raw_file(self, filename, preload=True, stim_channel='auto'):
        ext = filename.split('.')[-1]

        switcher = {
            'edf': mne.io.read_raw_edf,
            'eeg': mne.io.read_raw_brainvision,  # todo: check...
        }
        # Get the function from switcher dictionary
        mne_io_read_raw = switcher.get(ext, lambda: "nothing")
        # Execute the function
        return mne_io_read_raw(filename, preload=preload, stim_channel=stim_channel)

    def _get_concatenated_raw_file(self, filenames):
        raw_list = [self._open_raw_file(file) for file in filenames if
                    self.get_subject_number(file) not in self._drop_subject]
        raw = mne.io.concatenate_raws(raw_list)
        return raw

    @staticmethod
    def _find_filenames(rec_nums, filenames):
        import re
        files = []
        for i in rec_nums:
            for fname in filenames:
                res = re.findall(r'.*R{:02d}.*'.format(i), fname)
                if res:
                    files.append(res[0])
        # files = [ for i in rec_nums for fname in filenames]
        return files

    @staticmethod
    def _get_num_with_predefined_char(filename, char, required_num='required'):
        """
        Searches for number in filename

        :param char: character to search for
        :param required_num: string to print in error message
        :return: number after given char
        :raises FileNotFoundError if none numbers were found
        """
        import re
        num_list = re.findall(r'.*' + char + '\d+', filename)
        if not num_list:
            raise FileNotFoundError(
                "Can not give back {} number: filename '{}' does not contain '{}' character.".format(required_num,
                                                                                                     filename,
                                                                                                     char))
        num_str = num_list[0]
        num_ind = num_str.rfind(char) - len(num_str) + 1
        return int(num_str[num_ind:])

    @staticmethod
    def get_record_number(filename):
        """
        Only works if record number is stored in filename:
            *R<record num>*

        :return: record number from filename
        """
        return OfflineEpochCreator._get_num_with_predefined_char(filename, 'R', "RECORD")

    @staticmethod
    def get_subject_number(filename):
        """
        Only works if subject number is stored in filename:
            *S<record num>*

        :return: record number from filename
        """
        return OfflineEpochCreator._get_num_with_predefined_char(filename, 'S', "SUBJECT")

    def _create_epochs_from_db(self):
        filenames = self._get_filenames()
        # TODO: sort filenames by TRIGGER_TASK_LIST + subject

        # TODO: filter for real and img
        # TODO: frep missmatch...
        # TODO: drop wrong...
        for tasks in self._trigger_task_list:
            files = self._find_filenames(tasks, filenames)

            raw = self._get_concatenated_raw_file(files)
            events = mne.find_events(raw, shortest_event=0, stim_channel='STI 014')
            print(events)
            # picks = mne.pick_types(raw.info, meg=False, eeg=True, stim=False, eog=False,
            #                    exclude='bads')
            # epochs = mne.Epochs(raw, events, event_id, tmin, tmax, proj=True, picks=picks,
            #                 baseline=None, preload=True)

    def _create_annotated_db(self):
        filenames = self._get_filenames()
        for file in filenames:
            rec_num = self.get_record_number(file)
            subj_num = self.get_subject_number(file)

            if subj_num in self._drop_subject:
                continue


if __name__ == '__main__':
    # base_dir = "D:/BCI_stuff/databases/"  # MTA TTK
    # base_dir = 'D:/Csabi/'  # Home
    # base_dir = "D:/Users/Csabi/data"  # ITK
    base_dir = "/home/csabi/databases/"  # linux

    proc = OfflineEpochCreator(base_dir).use_physionet()
    proc.run()
