import socket
from itertools import cycle

from numpy import uint8

from bionic_apps.games.braindriver.commands import ControlCommand
from bionic_apps.games.braindriver.logger import setup_logger, log_info

GAME_CONTROL_PORT = 5555
LOGGER_NAME = 'GameControl'


class GameControl:

    def __init__(self, player_num=1, udp_ip='localhost', udp_port=GAME_CONTROL_PORT,
                 make_log=False, log_to_stream=False, game_log_conn=None):
        self.udp_ip = udp_ip
        self.udp_port = udp_port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.player_num = player_num
        self._log = make_log
        self._command_menu = cycle([ControlCommand.LEFT, ControlCommand.RIGHT, ControlCommand.HEADLIGHT])
        self._game_log_conn = game_log_conn
        if make_log:
            setup_logger(LOGGER_NAME, log_to_stream=log_to_stream)

    def _send_message(self, message):
        self.socket.sendto(message, (self.udp_ip, self.udp_port))

    def _log_message(self, message):
        if self._log:
            log_info(LOGGER_NAME, message)

    def turn_left(self):
        self._send_message(uint8(self.player_num * 10 + ControlCommand.LEFT.value))
        self._log_message('Command: Left turn')

    def turn_right(self):
        self._send_message(uint8(self.player_num * 10 + ControlCommand.RIGHT.value))
        self._log_message('Command: Right turn')

    def turn_light_on(self):
        self._send_message(uint8(self.player_num * 10 + ControlCommand.HEADLIGHT.value))
        self._log_message('Command: Light on')

    def go_straight(self):
        # do not sed anything because it will be registered as wrong command...
        self._log_message('Command: Go straight')

    def game_started(self):
        self._log_message('Game started!')

    def control_game(self, command):
        if command == ControlCommand.LEFT:
            self.turn_left()
        elif command == ControlCommand.RIGHT:
            self.turn_right()
        elif command == ControlCommand.HEADLIGHT:
            self.turn_light_on()
        elif command == ControlCommand.STRAIGHT:
            self.go_straight()
        else:
            raise NotImplementedError('Command {} is not implemented'.format(command))

    def control_game_with_2_opt(self, switch_cmd=False):
        if switch_cmd:
            cmd = next(self._command_menu)
        else:
            cmd = ControlCommand.STRAIGHT
        self.control_game(cmd)

        if self._log and self._game_log_conn is not None:
            # self._game_logger.log_toggle_switch(cmd)
            self._game_log_conn.send(['log', cmd])


def run_demo(make_log=False):
    from pynput.keyboard import Key, Listener

    controller = GameControl(make_log=make_log)

    def control(key):
        if key == Key.up:
            controller.turn_light_on()
        elif key == Key.left:
            controller.turn_left()
        elif key == Key.right:
            controller.turn_right()

    def on_press(key):
        control(key)
        print('{0} pressed'.format(
            key))

    def on_release(key):
        # print('{0} release'.format(
        #     key))
        if key == Key.esc:
            # Stop listener
            return False

    # Collect events until released
    with Listener(
            on_press=on_press,
            on_release=on_release) as listener:
        listener.join()


if __name__ == '__main__':
    run_demo()
