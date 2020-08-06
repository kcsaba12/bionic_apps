import unittest
from multiprocessing import Process
from pathlib import PurePath

import timeout_decorator

from BCISystem import BCISystem, Databases, FeatureType, XvalidateMethod
from online.DataSender import run as send_online_data
from preprocess import init_base_config


# @unittest.skip("Not interested")
class TestOfflineBciSystem(unittest.TestCase):

    def setUp(self):
        self.bci = BCISystem()

    def test_subject_x_val_fft_power(self):
        feature_extraction = dict(
            feature_type=FeatureType.FFT_POWER,
            fft_low=14, fft_high=30
        )
        self.assertIsNone(self.bci.offline_processing(
            Databases.GAME_PAR_D, feature_params=feature_extraction,
            epoch_tmin=0, epoch_tmax=4,
            window_length=1, window_step=.1,
            method=XvalidateMethod.SUBJECT,
            subject=1,
            make_binary_classification=True
        ))

    def test_subject_x_val_fft_range(self):
        feature_extraction = dict(
            feature_type=FeatureType.FFT_RANGE,
            fft_low=14, fft_high=30, fft_step=2, fft_width=2
        )
        self.assertIsNone(self.bci.offline_processing(
            Databases.GAME_PAR_D, feature_params=feature_extraction,
            epoch_tmin=0, epoch_tmax=4,
            window_length=1, window_step=.1,
            method=XvalidateMethod.SUBJECT,
            subject=1,
            make_binary_classification=True
        ))

    def test_subject_x_val_multi_fft_power(self):
        feature_extraction = dict(
            feature_type=FeatureType.MULTI_FFT_POWER,
            fft_ranges=[(14, 36), (18, 32), (18, 36), (22, 28),
                        (22, 32), (22, 36), (26, 32), (26, 36)]
        )
        self.assertIsNone(self.bci.offline_processing(
            Databases.GAME_PAR_D, feature_params=feature_extraction,
            epoch_tmin=0, epoch_tmax=4,
            window_length=1, window_step=.1,
            method=XvalidateMethod.SUBJECT,
            subject=1,
            make_binary_classification=True
        ))


class TestOnlineBci(unittest.TestCase):
    _live_eeg_emulator = Process()

    @classmethod
    def setUpClass(cls):
        cls._path = PurePath(init_base_config())
        cls._path = cls._path.joinpath('Game', 'paradigmD', 'subject2')
        cls._live_eeg_emulator = Process(target=send_online_data,
                                         kwargs=dict(filename=cls._path.joinpath('game01.vhdr'), get_labels=False,
                                                     add_extra_data=True))
        cls._live_eeg_emulator.start()

    @classmethod
    def tearDownClass(cls):
        cls._live_eeg_emulator.terminate()

    def setUp(self):
        self.bci = BCISystem()

    @timeout_decorator.timeout(15)
    def test_play_game(self):
        feature_extraction = dict(
            feature_type=FeatureType.MULTI_FFT_POWER,
            fft_ranges=[(14, 36), (18, 32), (18, 36), (22, 28),
                        (22, 32), (22, 36), (26, 32), (26, 36)]
        )
        with self.assertRaises(timeout_decorator.TimeoutError):
            self.bci.play_game(
                Databases.GAME_PAR_D, feature_params=feature_extraction,
                epoch_tmin=0, epoch_tmax=4,
                window_length=1, window_step=.1,
                train_file=self._path.joinpath('rec01.vhdr').as_posix()
            )


if __name__ == '__main__':
    unittest.main()
