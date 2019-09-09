import time
import threading
import numpy as np
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score

import ai
import online
from config import *
from preprocess import OfflineDataPreprocessor, SubjectKFold, save_pickle_data, load_pickle_data

AI_MODEL = 'ai.model'


class BCISystem(object):

    def __init__(self, base_dir="", window_length=0.5, window_step=0.25):
        """ Constructor for BCI system

        Parameters
        ----------
        base_dir: str
            absolute path to base dir of database
        window_length: float
            length of eeg processor window in seconds
        window_step: float
            window shift in seconds
        """
        self._base_dir = base_dir
        self._window_length = window_length
        self._window_step = window_step
        self._proc = None

    def _subject_crossvalidate(self, subj_n_fold_num=None, save_model=False):
        kfold = SubjectKFold(subj_n_fold_num)
        ai_model = dict()

        for train_x, train_y, test_x, test_y, subject in kfold.split(self._proc):
            t = time.time()
            svm = ai.SVM(C=1, cache_size=4000, random_state=12, class_weight={REST: 0.25})
            # svm = ai.LinearSVM(C=1, random_state=12, max_iter=20000, class_weight={REST: 0.25})
            # svm = ai.libsvm_SVC(C=1, cache_size=4000, class_weight={REST: 0.25})
            # svm = ai.libsvm_cuda(C=1, cache_size=4000, class_weight={REST: 0.25})
            # svm.set_labels(labels)
            svm.fit(train_x, train_y)
            t = time.time() - t
            print("Training elapsed {} seconds.".format(t))
            ai_model[subject] = svm

            y_pred = svm.predict(test_x)

            class_report = classification_report(test_y, y_pred)
            conf_martix = confusion_matrix(test_y, y_pred)
            acc = accuracy_score(test_y, y_pred)

            print("Classification report for subject{}:".format(subject))
            print("classifier %s:\n%s\n"
                  % (self, class_report))
            print("Confusion matrix:\n%s\n" % conf_martix)
            print("Accuracy score: {}\n".format(acc))

        if save_model:
            save_pickle_data(ai_model, self._proc.proc_db_path + AI_MODEL)

    def _init_db_processor(self, db_name, epoch_tmin=0, epoch_tmax=3, use_drop_subject_list=True, fast_load=True):
        if self._proc is None:
            self._proc = OfflineDataPreprocessor(self._base_dir, epoch_tmin, epoch_tmax, use_drop_subject_list,
                                                 self._window_length, self._window_step, fast_load)
            if db_name == 'physionet':
                self._proc.use_physionet()
                # labels = [REST, LEFT_HAND, RIGHT_HAND, BOTH_LEGS, BOTH_HANDS]
            elif db_name == 'pilot':
                self._proc.use_pilot()
                # labels = [REST, LEFT_HAND, RIGHT_HAND, BOTH_LEGS, BOTH_HANDS]
            else:
                raise NotImplementedError('Database processor for {} db is not implemented'.format(db_name))

    def offline_processing(self, db_name='physionet', feature='avg_column', method='subjectXvalidate', epoch_tmin=0,
                           epoch_tmax=3, use_drop_subject_list=True, fast_load=True, subj_n_fold_num=None):

        self._init_db_processor(db_name, epoch_tmin, epoch_tmax, use_drop_subject_list, fast_load)
        self._proc.run(feature=feature)

        if method == 'subjectXvalidate':
            self._subject_crossvalidate(subj_n_fold_num)

        elif method == 'trainSVM':
            self._subject_crossvalidate(save_model=True)

        else:
            raise NotImplementedError('Method {} is not implemented'.format(method))

    def online_processing(self, db_name, subject, feature='avg_column', get_real_labels=False, data_sender=None):
        from pylsl import LostError
        self._init_db_processor(db_name)
        self._proc.init_processed_db_path(feature)
        ai_model = load_pickle_data(self._proc.proc_db_path + AI_MODEL)
        svm = ai_model[subject]
        dsp = online.DSP()
        dsp.start_signal_recording()
        sleep_time = 1 / dsp.fs

        y_preds = list()
        y_real = list()
        label = None

        while data_sender is None or data_sender.is_alive():
            t = time.time()

            if get_real_labels:
                data, label = dsp.get_eeg_window(self._window_length, get_real_labels)
            else:
                data = dsp.get_eeg_window(self._window_length)

            sh = np.shape(data)
            if len(sh) < 2 or sh[1] / dsp.fs < self._window_length:
                # The data is still not big enough for window.
                continue

            # todo: generalize, similar function in preprocessor _get_windowed_features()
            if feature == 'avg_column':
                data = np.average(data, axis=1)
                data = data.reshape((1, -1))
            else:
                raise NotImplementedError('{} feature creation is not implemented'.format(feature))

            y_pred = svm.predict(data)

            y_real.append(label)
            y_preds.append(y_pred)

            time.sleep(max(0, sleep_time - (time.time() - t)))

        return y_preds, y_real


def calc_online_acc(y_pred, y_real):
    from config import PilotDB
    conv = {val: key for key, val in PilotDB.TRIGGER_TASK_CONVERTER.items()}
    y_real = [conv.get(y, REST) for y in y_real]
    class_report = classification_report(y_real, y_pred)
    conf_martix = confusion_matrix(y_real, y_pred)
    acc = accuracy_score(y_real, y_pred)

    print("%s\n" % class_report)
    print("Confusion matrix:\n%s\n" % conf_martix)
    print("Accuracy score: {}\n".format(acc))


if __name__ == '__main__':
    base_dir = "D:/BCI_stuff/databases/"  # MTA TTK
    # base_dir = 'D:/Csabi/'  # Home
    # base_dir = "D:/Users/Csabi/data/"  # ITK
    # base_dir = "/home/csabi/databases/"  # linux

    bci = BCISystem(base_dir)
    db_name = 'pilot'
    # bci.offline_processing(db_name=db_name, feature='avg_column', fast_load=True, method='trainSVM')

    train_subj = 1
    test_subj = 4
    file = '{}Cybathlon_pilot/pilot{}/rec01.vhdr'.format(base_dir, test_subj)
    get_real_labels = True
    thread = threading.Thread(target=online.DataSender.run, args=(file, get_real_labels), daemon=True)
    thread.start()
    y_preds, y_real = bci.online_processing(db_name=db_name, subject=train_subj, get_real_labels=get_real_labels,
                                            data_sender=thread)
    print(len(y_preds), len(y_real))
    calc_online_acc(y_preds, y_real)
